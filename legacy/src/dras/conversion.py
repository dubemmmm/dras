from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz


class ConversionError(RuntimeError):
    pass


def _validate_pdf(path: Path) -> bytes:
    if not path.exists() or path.stat().st_size < 500:
        raise ConversionError("The converter did not produce a PDF")
    payload = path.read_bytes()
    try:
        document = fitz.open(stream=payload, filetype="pdf")
        if document.page_count < 1:
            raise ConversionError("The converted PDF contains no pages")
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError("The converter produced an invalid PDF") from exc
    return payload


def _libreoffice_pdf(source: Path, output_dir: Path) -> bytes | None:
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if not executable:
        return None
    profile = output_dir / "lo-profile"
    try:
        result = subprocess.run(
            [
                executable,
                "--headless",
                "--safe-mode",
                f"-env:UserInstallation=file://{profile}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(source),
            ],
            capture_output=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError("LibreOffice conversion timed out") from exc
    except OSError as exc:
        raise ConversionError("LibreOffice could not be started") from exc
    if result.returncode:
        raise ConversionError("LibreOffice could not convert the Word document")
    return _validate_pdf(output_dir / f"{source.stem}.pdf")


def _microsoft_word_pdf(source: Path, output_dir: Path) -> bytes | None:
    word = Path("/Applications/Microsoft Word.app")
    osascript = shutil.which("osascript")
    if sys.platform != "darwin" or not word.exists() or not osascript:
        return None
    target = output_dir / "rendered.pdf"
    # Use Word's own PDF renderer. JXA is considerably less brittle than Word's
    # AppleScript terminology and is the same approach used by docx2pdf on macOS.
    script = """
function run(argv) {
    const inputPath = Path(argv[0]).toString();
    const outputPath = Path(argv[1]).toString();
    const word = Application("Microsoft Word");
    word.activate();
    delay(1);
    word.open(inputPath);
    const document = word.activeDocument;
    try {
        document.saveAs({fileName: outputPath, fileFormat: "format PDF"});
    } finally {
        document.close({saving: "no"});
    }
}
"""
    try:
        result = subprocess.run(
            [osascript, "-l", "JavaScript", "-", str(source), str(target)],
            input=script,
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(
            "Microsoft Word conversion timed out. Close any open Word dialogs and try again."
        ) from exc
    except OSError as exc:
        raise ConversionError("Microsoft Word automation could not be started") from exc
    if result.returncode:
        message = f"{result.stdout}\n{result.stderr}".lower()
        if "not authorized" in message or "-1743" in message:
            raise ConversionError(
                "macOS blocked Microsoft Word automation. Allow your terminal or Python "
                "to control Microsoft Word in System Settings > Privacy & Security > Automation."
            )
        if "application can’t be found" in message or "application can't be found" in message:
            raise ConversionError("Microsoft Word is installed but macOS could not open it")
        raise ConversionError(
            "Microsoft Word could not export this document. Open Word once, dismiss any "
            "startup or document-recovery dialogs, then try Convert to PDF again."
        )
    return _validate_pdf(target)


def convert_office_to_pdf(filename: str, data: bytes) -> bytes:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".doc", ".docx"}:
        raise ConversionError("Only Word .doc and .docx files require conversion")
    with tempfile.TemporaryDirectory(prefix="dras-office-") as folder:
        output_dir = Path(folder)
        source = output_dir / f"source{suffix}"
        source.write_bytes(data)
        converted = _libreoffice_pdf(source, output_dir)
        if converted is not None:
            return converted
        converted = _microsoft_word_pdf(source, output_dir)
        if converted is not None:
            return converted
    raise ConversionError("No supported Word-to-PDF converter is available")
