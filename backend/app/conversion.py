import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.conversion_storage import (
    conversion_output_path,
    delete_conversion_output,
    delete_user_conversion_outputs,
    store_conversion_output,
)
from app.database import get_db
from app.models import ConversionHistory, User
from app.schemas import ConversionHistoryResponse
from app.security import get_current_user, get_optional_current_user


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversions", tags=["konverziók"])
DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]

MAX_CONVERSION_FILE_SIZE_BYTES = 25 * 1024 * 1024
MAX_DOCX_UNCOMPRESSED_SIZE_BYTES = 100 * 1024 * 1024
CONVERSION_TIMEOUT_SECONDS = 120
UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024
DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class ConversionUnavailableError(Exception):
    """A szükséges konverziós program nem érhető el."""


class ConversionTimeoutError(Exception):
    """A konverzió túllépte a megengedett futási időt."""


def _save_upload(upload: UploadFile, destination: Path) -> int:
    total_size = 0

    with destination.open("wb") as destination_file:
        while chunk := upload.file.read(UPLOAD_CHUNK_SIZE_BYTES):
            total_size += len(chunk)
            if total_size > MAX_CONVERSION_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="A fájl legfeljebb 25 MB lehet.",
                )
            destination_file.write(chunk)

    if total_size == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A feltöltött fájl üres.",
        )

    return total_size


def _validate_pdf(path: Path) -> None:
    with path.open("rb") as pdf_file:
        header = pdf_file.read(1024)

    if b"%PDF-" not in header:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A feltöltött fájl nem érvényes PDF.",
        )


def _validate_docx(path: Path) -> None:
    try:
        with ZipFile(path) as document:
            content_names = set(document.namelist())
            expanded_size = sum(item.file_size for item in document.infolist())
    except (BadZipFile, OSError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A feltöltött fájl nem érvényes DOCX dokumentum.",
        ) from None

    required_names = {"[Content_Types].xml", "word/document.xml"}
    if not required_names.issubset(content_names):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A feltöltött fájl nem érvényes DOCX dokumentum.",
        )

    if expanded_size > MAX_DOCX_UNCOMPRESSED_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="A DOCX dokumentum kicsomagolt mérete túl nagy.",
        )


def _run_conversion_command(command: list[str], workspace: Path) -> None:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=CONVERSION_TIMEOUT_SECONDS,
            env={**os.environ, "HOME": str(workspace)},
        )
    except subprocess.TimeoutExpired as error:
        raise ConversionTimeoutError from error
    except FileNotFoundError as error:
        raise ConversionUnavailableError from error

    if result.returncode != 0:
        raise RuntimeError("A konverziós program hibát jelzett.")


def _find_pdf2docx() -> str:
    executable = shutil.which("pdf2docx")
    if executable:
        return executable

    script_directory = Path(sys.executable).parent
    for executable_name in ("pdf2docx", "pdf2docx.exe"):
        candidate = script_directory / executable_name
        if candidate.is_file():
            return str(candidate)

    raise ConversionUnavailableError


def _convert_pdf_to_docx(source: Path, destination: Path, workspace: Path) -> None:
    _run_conversion_command(
        [_find_pdf2docx(), "convert", str(source), str(destination)],
        workspace,
    )


def _find_libreoffice() -> str:
    configured_binary = os.getenv("LIBREOFFICE_BIN")
    candidates = (
        [configured_binary]
        if configured_binary
        else ["libreoffice", "soffice"]
    )

    for candidate in candidates:
        if candidate:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved

    raise ConversionUnavailableError


def _convert_docx_to_pdf(source: Path, destination: Path, workspace: Path) -> None:
    libreoffice = _find_libreoffice()
    output_directory = workspace / "libreoffice-output"
    profile_directory = workspace / "libreoffice-profile"
    output_directory.mkdir()

    _run_conversion_command(
        [
            libreoffice,
            f"-env:UserInstallation={profile_directory.as_uri()}",
            "--headless",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(output_directory),
            str(source),
        ],
        workspace,
    )

    generated_pdf = output_directory / f"{source.stem}.pdf"
    if not generated_pdf.is_file():
        raise RuntimeError("LibreOffice nem tudta átalakítani a dokumentumot.")

    generated_pdf.replace(destination)


def _convert_upload(
    upload: UploadFile,
    *,
    input_extension: str,
    output_extension: str,
    output_media_type: str,
    converter: Callable[[Path, Path, Path], None],
    current_user: User | None,
    database: Session,
) -> FileResponse:
    workspace = Path(tempfile.mkdtemp(prefix="document-conversion-"))

    try:
        filename = upload.filename or ""
        if Path(filename).suffix.lower() != input_extension:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Ehhez a konverzióhoz {input_extension} fájl szükséges.",
            )

        source_filename = _safe_source_filename(filename, input_extension)
        source_stem = Path(source_filename).stem[:245] or "document"
        output_filename = f"{source_stem}{output_extension}"
        source = workspace / f"source{input_extension}"
        destination = workspace / output_filename
        _save_upload(upload, source)

        if input_extension == ".pdf":
            _validate_pdf(source)
        else:
            _validate_docx(source)

        try:
            converter(source, destination, workspace)
        except ConversionUnavailableError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="A konverziós szolgáltatás jelenleg nem érhető el.",
            ) from None
        except ConversionTimeoutError:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="A konverzió túllépte a megengedett időt.",
            ) from None
        except Exception:
            logger.exception("A dokumentum konvertálása sikertelen.")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Nem sikerült feldolgozni a dokumentumot. Ellenőrizd a fájlt.",
            ) from None

        if not destination.is_file() or destination.stat().st_size == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Nem sikerült feldolgozni a dokumentumot. Ellenőrizd a fájlt.",
            )

        response_path = destination
        response_background = BackgroundTask(
            shutil.rmtree,
            workspace,
            ignore_errors=True,
        )
        if current_user is not None:
            response_path = _store_history(
                database=database,
                user=current_user,
                source_filename=source_filename,
                direction=f"{input_extension[1:]}-to-{output_extension[1:]}",
                output_filename=output_filename,
                output_path=destination,
            )
        return FileResponse(
            response_path,
            media_type=output_media_type,
            filename=output_filename,
            background=response_background,
        )
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    finally:
        upload.file.close()


def _safe_source_filename(filename: str, input_extension: str) -> str:
    normalized_filename = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    printable_filename = "".join(
        character for character in normalized_filename if character.isprintable()
    ).strip(" .")
    if not printable_filename:
        return f"document{input_extension}"
    return printable_filename[:255]


def _store_history(
    *,
    database: Session,
    user: User,
    source_filename: str,
    direction: str,
    output_filename: str,
    output_path: Path,
) -> Path:
    stored_path: Path | None = None
    try:
        storage_key, stored_path = store_conversion_output(
            user.id,
            output_path,
            Path(output_filename).suffix.lower(),
        )
        history_entry = ConversionHistory(
            user_id=user.id,
            source_filename=source_filename,
            direction=direction,
            output_filename=output_filename,
            storage_key=storage_key,
            output_size_bytes=stored_path.stat().st_size,
        )
        database.add(history_entry)
        database.commit()
    except (OSError, SQLAlchemyError):
        database.rollback()
        if stored_path is not None:
            try:
                stored_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Nem sikerült eltávolítani a félbemaradt fájlt.")
        logger.exception("Nem sikerült elmenteni a konverziós előzményt.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nem sikerült elmenteni a konvertált fájlt.",
        ) from None

    return stored_path


@router.get(
    "/history",
    response_model=list[ConversionHistoryResponse],
    summary="Saját konverziós előzmények lekérése",
)
def get_conversion_history(
    current_user: CurrentUser,
    database: DatabaseSession,
) -> list[ConversionHistory]:
    return list(
        database.scalars(
            select(ConversionHistory)
            .where(ConversionHistory.user_id == current_user.id)
            .order_by(
                ConversionHistory.created_at.desc(),
                ConversionHistory.id.desc(),
            )
        ).all()
    )


@router.delete(
    "/history",
    summary="Saját konverziós előzmények törlése",
)
def clear_conversion_history(
    current_user: CurrentUser,
    database: DatabaseSession,
) -> dict[str, int]:
    result = database.execute(
        delete(ConversionHistory).where(ConversionHistory.user_id == current_user.id)
    )
    database.commit()
    delete_user_conversion_outputs(current_user.id)
    return {"deleted_count": result.rowcount or 0}


@router.get(
    "/history/{conversion_id}/download",
    response_class=FileResponse,
    summary="Konverziós eredmény letöltése",
)
def download_conversion(
    conversion_id: int,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> FileResponse:
    history_entry = database.scalar(
        select(ConversionHistory).where(
            ConversionHistory.id == conversion_id,
            ConversionHistory.user_id == current_user.id,
        )
    )
    if history_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A konverziós előzmény nem található.",
        )

    output_path = conversion_output_path(current_user.id, history_entry.storage_key)
    if output_path is None or not output_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A konvertált fájl nem található.",
        )

    media_type = (
        DOCX_MIME_TYPE
        if history_entry.direction == "pdf-to-docx"
        else "application/pdf"
    )
    return FileResponse(
        output_path,
        media_type=media_type,
        filename=history_entry.output_filename,
    )


@router.delete(
    "/history/{conversion_id}",
    summary="Egy saját konverziós előzmény törlése",
)
def delete_conversion_history_entry(
    conversion_id: int,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> dict[str, str]:
    history_entry = database.scalar(
        select(ConversionHistory).where(
            ConversionHistory.id == conversion_id,
            ConversionHistory.user_id == current_user.id,
        )
    )
    if history_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="A konverziós előzmény nem található.",
        )

    storage_key = history_entry.storage_key
    database.delete(history_entry)
    database.commit()
    try:
        delete_conversion_output(current_user.id, storage_key)
    except OSError:
        logger.exception("Nem sikerült törölni a konverziós eredményfájlt.")

    return {"status": "deleted"}


@router.post(
    "/pdf-to-docx",
    response_class=FileResponse,
    summary="PDF átalakítása DOCX dokumentummá",
)
def pdf_to_docx(
    current_user: OptionalUser,
    database: DatabaseSession,
    file: UploadFile = File(...),
) -> FileResponse:
    return _convert_upload(
        file,
        input_extension=".pdf",
        output_extension=".docx",
        output_media_type=DOCX_MIME_TYPE,
        converter=_convert_pdf_to_docx,
        current_user=current_user,
        database=database,
    )


@router.post(
    "/docx-to-pdf",
    response_class=FileResponse,
    summary="DOCX dokumentum átalakítása PDF-fé",
)
def docx_to_pdf(
    current_user: OptionalUser,
    database: DatabaseSession,
    file: UploadFile = File(...),
) -> FileResponse:
    return _convert_upload(
        file,
        input_extension=".docx",
        output_extension=".pdf",
        output_media_type="application/pdf",
        converter=_convert_docx_to_pdf,
        current_user=current_user,
        database=database,
    )
