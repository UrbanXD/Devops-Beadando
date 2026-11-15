import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversions", tags=["konverziók"])

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
            status_code=status.HTTP_413_CONTENT_CONTENT_TOO_LARGE,
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
    output_filename: str,
    output_media_type: str,
    converter: Callable[[Path, Path, Path], None],
) -> FileResponse:
    workspace = Path(tempfile.mkdtemp(prefix="document-conversion-"))

    try:
        filename = upload.filename or ""
        if Path(filename).suffix.lower() != input_extension:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Ehhez a konverzióhoz {input_extension} fájl szükséges.",
            )

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

        return FileResponse(
            destination,
            media_type=output_media_type,
            filename=output_filename,
            background=BackgroundTask(
                shutil.rmtree,
                workspace,
                ignore_errors=True,
            ),
        )
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    finally:
        upload.file.close()


@router.post(
    "/pdf-to-docx",
    response_class=FileResponse,
    summary="PDF átalakítása DOCX dokumentummá",
)
def pdf_to_docx(
    file: UploadFile = File(...),
) -> FileResponse:
    return _convert_upload(
        file,
        input_extension=".pdf",
        output_filename="converted.docx",
        output_media_type=DOCX_MIME_TYPE,
        converter=_convert_pdf_to_docx,
    )


@router.post(
    "/docx-to-pdf",
    response_class=FileResponse,
    summary="DOCX dokumentum átalakítása PDF-fé",
)
def docx_to_pdf(
    file: UploadFile = File(...),
) -> FileResponse:
    return _convert_upload(
        file,
        input_extension=".docx",
        output_filename="converted.pdf",
        output_media_type="application/pdf",
        converter=_convert_docx_to_pdf,
    )
