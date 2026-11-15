import io
import subprocess
import zipfile
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import conversion, conversion_storage


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


def test_guest_can_convert_pdf_to_docx_without_saving_history(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(conversion_storage, "STORAGE_PATH", tmp_path)
    response = client.post(
        "/api/conversions/pdf-to-docx",
        files={"file": ("source.pdf", make_pdf(), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(conversion.DOCX_MIME_TYPE)
    assert 'filename="source.docx"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as document:
        assert "word/document.xml" in document.namelist()
    assert not (tmp_path / "conversions").exists()


def test_guest_can_convert_docx_to_pdf_using_libreoffice(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(conversion_storage, "STORAGE_PATH", tmp_path)
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
    assert 'filename="source.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")
    assert "--headless" in command_arguments
    assert "pdf:writer_pdf_Export" in command_arguments
    assert not (tmp_path / "conversions").exists()


def test_logged_in_conversion_is_saved_and_can_be_downloaded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(conversion_storage, "STORAGE_PATH", tmp_path)
    output_content = b"%PDF-1.7\nconverted document"

    def fake_converter(_source: Path, destination: Path, _workspace: Path) -> None:
        destination.write_bytes(output_content)

    monkeypatch.setattr(conversion, "_convert_docx_to_pdf", fake_converter)

    registered = client.post(
        "/api/auth/register",
        json={"email": "history@example.com", "password": "super-secret-password"},
    )
    assert registered.status_code == 201
    authorization = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    converted = client.post(
        "/api/conversions/docx-to-pdf",
        headers=authorization,
        files={"file": ("source.docx", make_docx(), conversion.DOCX_MIME_TYPE)},
    )

    assert converted.status_code == 200
    assert converted.content == output_content

    history = client.get("/api/conversions/history", headers=authorization)
    assert history.status_code == 200
    assert len(history.json()) == 1
    entry = history.json()[0]
    assert entry["source_filename"] == "source.docx"
    assert entry["direction"] == "docx-to-pdf"
    assert entry["output_filename"] == "source.pdf"
    assert entry["output_size_bytes"] == len(output_content)

    downloaded = client.get(
        f"/api/conversions/history/{entry['id']}/download",
        headers=authorization,
    )
    assert downloaded.status_code == 200
    assert downloaded.content == output_content
    assert 'filename="source.pdf"' in downloaded.headers["content-disposition"]


def test_logged_in_pdf_to_docx_conversion_is_saved(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(conversion_storage, "STORAGE_PATH", tmp_path)
    output_content = b"saved DOCX document"

    def fake_converter(_source: Path, destination: Path, _workspace: Path) -> None:
        destination.write_bytes(output_content)

    monkeypatch.setattr(conversion, "_convert_pdf_to_docx", fake_converter)
    registered = client.post(
        "/api/auth/register",
        json={
            "email": "pdf-history@example.com",
            "password": "super-secret-password",
        },
    )
    assert registered.status_code == 201
    authorization = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    converted = client.post(
        "/api/conversions/pdf-to-docx",
        headers=authorization,
        files={"file": ("report.pdf", make_pdf(), "application/pdf")},
    )

    assert converted.status_code == 200
    assert converted.content == output_content
    history = client.get("/api/conversions/history", headers=authorization)
    assert history.status_code == 200
    assert history.json()[0]["source_filename"] == "report.pdf"
    assert history.json()[0]["direction"] == "pdf-to-docx"
    assert history.json()[0]["output_filename"] == "report.docx"
    assert history.json()[0]["output_size_bytes"] == len(output_content)


def test_conversion_history_is_private_and_removed_with_account(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(conversion_storage, "STORAGE_PATH", tmp_path)
    output_content = b"%PDF-1.7\nprivate document"

    def fake_converter(_source: Path, destination: Path, _workspace: Path) -> None:
        destination.write_bytes(output_content)

    monkeypatch.setattr(conversion, "_convert_docx_to_pdf", fake_converter)
    owner_register = client.post(
        "/api/auth/register",
        json={"email": "owner@example.com", "password": "super-secret-password"},
    )
    assert owner_register.status_code == 201
    owner_authorization = {
        "Authorization": f"Bearer {owner_register.json()['access_token']}"
    }
    converted = client.post(
        "/api/conversions/docx-to-pdf",
        headers=owner_authorization,
        files={"file": ("private.docx", make_docx(), conversion.DOCX_MIME_TYPE)},
    )
    assert converted.status_code == 200
    entry = client.get(
        "/api/conversions/history", headers=owner_authorization
    ).json()[0]
    stored_file = next((tmp_path / "conversions").glob("*/*.pdf"))

    other_register = client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "password": "super-secret-password"},
    )
    assert other_register.status_code == 201
    other_authorization = {
        "Authorization": f"Bearer {other_register.json()['access_token']}"
    }

    assert client.get(
        "/api/conversions/history", headers=other_authorization
    ).json() == []
    assert client.get(
        f"/api/conversions/history/{entry['id']}/download",
        headers=other_authorization,
    ).status_code == 404
    assert client.get("/api/conversions/history").status_code == 401

    deleted = client.request(
        "DELETE",
        "/api/auth/me",
        headers=owner_authorization,
        json={"password": "super-secret-password"},
    )
    assert deleted.status_code == 200
    assert not stored_file.exists()


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
