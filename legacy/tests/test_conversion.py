from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from fastapi.testclient import TestClient

from dras import conversion
from dras.api import app, identity, service


def valid_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Rendered dissertation")
    return document.tobytes()


def test_word_conversion_prefers_libreoffice(monkeypatch):
    expected = valid_pdf()

    def fake_libreoffice(source: Path, output_dir: Path) -> bytes:
        assert source.name == "source.doc"
        assert source.read_bytes() == b"legacy word content"
        assert output_dir.exists()
        return expected

    monkeypatch.setattr(conversion, "_libreoffice_pdf", fake_libreoffice)
    monkeypatch.setattr(
        conversion,
        "_microsoft_word_pdf",
        lambda source, output_dir: pytest.fail("Word fallback should not run"),
    )

    assert conversion.convert_office_to_pdf("sample.doc", b"legacy word content") == expected


def test_word_conversion_reports_missing_converter(monkeypatch):
    monkeypatch.setattr(conversion, "_libreoffice_pdf", lambda source, output_dir: None)
    monkeypatch.setattr(conversion, "_microsoft_word_pdf", lambda source, output_dir: None)

    with pytest.raises(conversion.ConversionError, match="No supported"):
        conversion.convert_office_to_pdf("sample.docx", b"word content")


def test_microsoft_word_uses_native_jxa_pdf_export(monkeypatch, tmp_path):
    expected = valid_pdf()
    source = tmp_path / "source.doc"
    source.write_bytes(b"legacy word content")
    captured = {}
    real_exists = Path.exists

    def fake_exists(path):
        if str(path) == "/Applications/Microsoft Word.app":
            return True
        return real_exists(path)

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["script"] = kwargs["input"]
        Path(command[-1]).write_bytes(expected)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(conversion.sys, "platform", "darwin")
    monkeypatch.setattr(conversion.Path, "exists", fake_exists)
    monkeypatch.setattr(conversion.shutil, "which", lambda name: "/usr/bin/osascript")
    monkeypatch.setattr(conversion.subprocess, "run", fake_run)

    result = conversion._microsoft_word_pdf(source, tmp_path)

    assert result == expected
    assert captured["command"][1:3] == ["-l", "JavaScript"]
    assert 'fileFormat: "format PDF"' in captured["script"]


def test_conversion_rejects_non_word_input():
    with pytest.raises(conversion.ConversionError, match="Only Word"):
        conversion.convert_office_to_pdf("sample.pdf", valid_pdf())


def test_rendered_source_endpoint_returns_inline_pdf():
    expected = valid_pdf()

    class StubService:
        def rendered_source_bytes(self, assessment_id, owner):
            assert owner == "assessor@example.org"
            return expected

    app.dependency_overrides[identity] = lambda: "assessor@example.org"
    app.dependency_overrides[service] = StubService
    try:
        response = TestClient(app).get(
            "/v1/assessments/00000000-0000-0000-0000-000000000001/source/rendered"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.content == expected
