import os
import shutil
from pathlib import Path
from uuid import uuid4

from app.settings import STORAGE_PATH


ALLOWED_OUTPUT_EXTENSIONS = {".docx", ".pdf"}


def user_conversion_directory(user_id: int) -> Path:
    return STORAGE_PATH / "conversions" / str(user_id)


def store_conversion_output(
    user_id: int,
    source_path: Path,
    output_extension: str,
) -> tuple[str, Path]:
    if output_extension not in ALLOWED_OUTPUT_EXTENSIONS:
        raise ValueError("Unsupported conversion output extension.")

    user_directory = user_conversion_directory(user_id)
    user_directory.mkdir(parents=True, exist_ok=True)
    storage_key = f"{uuid4().hex}{output_extension}"
    destination = user_directory / storage_key
    temporary_path = user_directory / f".{storage_key}.tmp"

    try:
        shutil.copyfile(source_path, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)

    return storage_key, destination


def conversion_output_path(user_id: int, storage_key: str) -> Path | None:
    if (
        not storage_key
        or Path(storage_key).name != storage_key
        or Path(storage_key).suffix not in ALLOWED_OUTPUT_EXTENSIONS
    ):
        return None

    return user_conversion_directory(user_id) / storage_key


def delete_user_conversion_outputs(user_id: int) -> None:
    shutil.rmtree(user_conversion_directory(user_id), ignore_errors=True)


def delete_conversion_output(user_id: int, storage_key: str) -> None:
    output_path = conversion_output_path(user_id, storage_key)
    if output_path is not None:
        output_path.unlink(missing_ok=True)
        try:
            output_path.parent.rmdir()
        except OSError:
            pass
