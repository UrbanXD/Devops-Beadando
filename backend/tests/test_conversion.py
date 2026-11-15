import io
import subprocess
import zipfile
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import conversion


def make_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Konverziós tesztdokumentum")
    content = document.tobytes()
    document.close()
    return content


def make_docx() -> bytes:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as document:
        document.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
              <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
            </Types>""",
        )
        document.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body><w:p><w:r><w:t>Konverziós tesztdokumentum</w:t></w:r></w:p></w:body>
            </w:document>""",
        )
    return content.getvalue()


def test_guest_can_convert_pdf_to_docx(client: TestClient) -> None:
    response = client.post(
        "/api/conversions/pdf-to-docx",
        files={"file": ("source.pdf", make_pdf(), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(conversion.DOCX_MIME_TYPE)
    assert 'filename="converted.docx"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as document:
        assert "word/document.xml" in document.namelist()


def test_guest_can_convert_docx_to_pdf_using_libreoffice(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_arguments: list[str] = []

    def fake_which(_binary: str) -> str:
        return "/usr/bin/libreoffice"

    def fake_run(command: list[str], **_options: object) -> subprocess.CompletedProcess[str]:
        command_arguments.extend(command)
        output_directory = Path(command[command.index("--outdir") + 1])
        (output_directory / "source.pdf").write_bytes(b"%PDF-1.7\nconverted document")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(conversion.shutil, "which", fake_which)
    monkeypatch.setattr(conversion.subprocess, "run", fake_run)

    response = client.post(
        "/api/conversions/docx-to-pdf",
        files={
            "file": (
                "source.docx",
                make_docx(),
                conversion.DOCX_MIME_TYPE,
            )
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert 'filename="converted.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")
    assert "--headless" in command_arguments
    assert "pdf:writer_pdf_Export" in command_arguments


def test_conversion_rejects_wrong_extension(client: TestClient) -> None:
    response = client.post(
        "/api/conversions/pdf-to-docx",
        files={"file": ("source.docx", make_docx())},
    )

    assert response.status_code == 415


def test_conversion_rejects_invalid_pdf(client: TestClient) -> None:
    response = client.post(
        "/api/conversions/pdf-to-docx",
        files={"file": ("source.pdf", b"not a PDF")},
    )

    assert response.status_code == 422


def test_conversion_rejects_invalid_docx(client: TestClient) -> None:
    response = client.post(
        "/api/conversions/docx-to-pdf",
        files={"file": ("source.docx", b"not a DOCX")},
    )

    assert response.status_code == 422


def test_docx_to_pdf_returns_unavailable_without_libreoffice(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conversion.shutil, "which", lambda _binary: None)
    response = client.post(
        "/api/conversions/docx-to-pdf",
        files={"file": ("source.docx", make_docx())},
    )

    assert response.status_code == 503


def test_conversion_rejects_files_over_size_limit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conversion, "MAX_CONVERSION_FILE_SIZE_BYTES", 5)
    response = client.post(
        "/api/conversions/pdf-to-docx",
        files={"file": ("source.pdf", b"%PDF-1.7")},
    )

    assert response.status_code == 413
