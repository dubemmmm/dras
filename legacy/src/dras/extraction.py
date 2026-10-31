from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from collections import Counter

import fitz
from docx import Document

from dras.config import Settings
from dras.schemas import (
    Dissertation,
    DissertationSection,
    DocumentPage,
    ExtractionWarning,
    Metadata,
    MetadataExtraction,
    SectionType,
)

PDF_SIGNATURE = b"%PDF-"
DOCX_SIGNATURE = b"PK\x03\x04"
DOC_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
HEADING_PATTERNS: tuple[tuple[SectionType, re.Pattern[str]], ...] = (
    (SectionType.ABSTRACT, re.compile(r"^\s*abstract\s*$", re.I)),
    (SectionType.INTRODUCTION, re.compile(r"^\s*(chapter\s+(one|1)\s*[:.-]?\s*)?introduction\s*$", re.I)),
    (SectionType.LITERATURE_REVIEW, re.compile(r"^\s*(chapter\s+(two|2)\s*[:.-]?\s*)?literature\s+review\s*$", re.I)),
    (SectionType.METHODS, re.compile(r"^\s*(chapter\s+(three|3)\s*[:.-]?\s*)?(materials?\s+and\s+methods?|methodology|methods?)\s*$", re.I)),
    (SectionType.RESULTS, re.compile(r"^\s*(chapter\s+(four|4)\s*[:.-]?\s*)?results?(\s+and\s+findings)?\s*$", re.I)),
    (SectionType.DISCUSSION, re.compile(r"^\s*(chapter\s+(five|5)\s*[:.-]?\s*)?discussion\s*$", re.I)),
    (SectionType.CONCLUSION, re.compile(r"^\s*(conclusions?|summary,?\s+conclusion(s)?\s+and\s+recommendations?)\s*$", re.I)),
    (SectionType.REFERENCES, re.compile(r"^\s*(references|bibliography)\s*$", re.I)),
    (SectionType.APPENDICES, re.compile(r"^\s*append(?:ix|ices)(?:\s+[A-Z0-9]+)?\s*$", re.I)),
)


class DocumentRejected(ValueError):
    pass


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_upload(filename: str, content_type: str, data: bytes, settings: Settings) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix not in {"pdf", "docx", "doc"}:
        raise DocumentRejected("Only .pdf, .docx, and legacy .doc files are supported")
    if len(data) > settings.max_upload_bytes:
        raise DocumentRejected("File exceeds the 100 MB upload limit")
    if not data:
        raise DocumentRejected("The uploaded file is empty")
    if suffix == "pdf" and not data.startswith(PDF_SIGNATURE):
        raise DocumentRejected("The file signature does not match PDF")
    if suffix == "docx":
        if not data.startswith(DOCX_SIGNATURE):
            raise DocumentRejected("The file signature does not match DOCX")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
                if "word/document.xml" not in names:
                    raise DocumentRejected("Malformed DOCX archive")
                if any(name.lower().endswith("vbaproject.bin") for name in names):
                    raise DocumentRejected("Macro-enabled Word documents are not accepted")
                total_uncompressed = sum(item.file_size for item in archive.infolist())
                if total_uncompressed > max(settings.max_upload_bytes * 5, 250_000_000):
                    raise DocumentRejected("DOCX archive expands beyond the safety limit")
        except zipfile.BadZipFile as exc:
            raise DocumentRejected("Malformed DOCX archive") from exc
    if suffix == "doc" and not data.startswith(DOC_SIGNATURE):
        raise DocumentRejected("The file signature does not match legacy Word .doc")
    expected = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
    }[suffix]
    if content_type and content_type not in {expected, "application/octet-stream"}:
        raise DocumentRejected("Declared MIME type does not match the file extension")
    return expected


def _legacy_doc_text(data: bytes) -> str:
    with tempfile.TemporaryDirectory(prefix="dras-doc-") as folder:
        source = os.path.join(folder, "source.doc")
        with open(source, "wb") as handle:
            handle.write(data)
        textutil = shutil.which("textutil")
        if textutil:
            result = subprocess.run(
                [textutil, "-convert", "txt", "-stdout", source],
                capture_output=True,
                timeout=120,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.decode("utf-8", errors="replace")
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice:
            profile = os.path.join(folder, "profile")
            result = subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--safe-mode",
                    f"-env:UserInstallation=file://{profile}",
                    "--convert-to",
                    "txt:Text",
                    "--outdir",
                    folder,
                    source,
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
            target = os.path.join(folder, "source.txt")
            if result.returncode == 0 and os.path.exists(target):
                with open(target, encoding="utf-8", errors="replace") as handle:
                    return handle.read()
    raise DocumentRejected("Legacy .doc extraction requires macOS textutil or LibreOffice")


def _normalized_lines(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).replace("\u2028", "\n").replace("\u2029", "\n")
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def extract_metadata_from_text(text: str) -> MetadataExtraction:
    """Extract only explicit title-page metadata; ambiguous values remain blank."""
    lines = _normalized_lines(text)[:120]
    confidence: dict[str, float] = {}
    warnings: list[str] = []
    candidate_name = registration_number = dissertation_title = supervisor_name = None

    by_index = next((index for index, line in enumerate(lines) if re.fullmatch(r"BY", line, re.I)), None)
    if by_index is not None:
        for line in lines[by_index + 1 : by_index + 5]:
            if re.fullmatch(r"\(?[A-Z0-9][A-Z0-9 /._-]{2,}\)?", line, re.I) and not re.fullmatch(r"\(?\d{4,20}\)?", line):
                candidate_name = line.strip(" ()")
                confidence["candidate_name"] = 0.98
                break
        title_lines: list[str] = []
        for line in reversed(lines[max(0, by_index - 6) : by_index]):
            if re.search(r"WEST AFRICAN|FACULTY OF|COLLEGE OF PHARMACISTS", line, re.I):
                break
            if line.isupper() and len(line) > 8:
                title_lines.insert(0, line)
            elif title_lines:
                break
        if title_lines:
            dissertation_title = " ".join(title_lines)
            confidence["dissertation_title"] = 0.96

    labelled_candidate = re.search(r"(?im)^\s*(?:candidate|student)(?:'s)?\s+name\s*:\s*(.+)$", text)
    if not candidate_name and labelled_candidate:
        candidate_name = re.sub(r"\s+", " ", labelled_candidate.group(1)).strip()
        confidence["candidate_name"] = 0.95

    search_region = lines[by_index + 1 : by_index + 8] if by_index is not None else lines[:50]
    for line in search_region:
        match = re.search(r"\b(?:reg(?:istration)?\.?\s*(?:no\.?|number)?\s*[:#-]?\s*)?\(?([A-Z]*\d[A-Z0-9/-]{4,19})\)?\b", line, re.I)
        if match and not re.fullmatch(r"\(?(?:19|20)\d{2}\)?", line):
            registration_number = match.group(1)
            confidence["registration_number"] = 0.98 if line.startswith("(") else 0.9
            break

    for index, line in enumerate(lines[:80]):
        match = re.match(r"(?i)^\s*(?:name of\s+)?supervisor\s*:\s*(.*)$", line)
        if match:
            value = match.group(1).strip()
            if not value and index + 1 < len(lines):
                value = lines[index + 1]
            if value:
                supervisor_name = value
                confidence["supervisor_name"] = 0.98
            break

    values = {
        "candidate_name": candidate_name,
        "registration_number": registration_number,
        "dissertation_title": dissertation_title,
        "supervisor_name": supervisor_name,
    }
    missing = [name.replace("_", " ") for name, value in values.items() if not value]
    if missing:
        warnings.append(f"Could not confidently extract: {', '.join(missing)}. Please enter or confirm manually.")
    return MetadataExtraction(metadata=Metadata(**values), confidence=confidence, warnings=warnings)


def extract_title_page_metadata(filename: str, mime_type: str, data: bytes) -> MetadataExtraction:
    if mime_type == "application/pdf":
        try:
            document = fitz.open(stream=data, filetype="pdf")
            if document.needs_pass:
                raise DocumentRejected("Encrypted PDFs are not accepted")
            text = "\n\f\n".join(document[index].get_text("text") for index in range(min(3, document.page_count)))
        except DocumentRejected:
            raise
        except Exception as exc:
            raise DocumentRejected("PDF is malformed or unreadable") from exc
    elif mime_type == "application/msword":
        text = _legacy_doc_text(data).split("\f", 1)[0]
    else:
        try:
            document = Document(io.BytesIO(data))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs[:120])
        except Exception as exc:
            raise DocumentRejected("DOCX is malformed or unreadable") from exc
    result = extract_metadata_from_text(text)
    if mime_type == "application/msword":
        result.warnings.append("Legacy .doc support is intended for the local pilot; convert to DOCX or PDF for reliable page mapping.")
    return result


def _strip_repeated_margins(page_texts: list[str]) -> list[str]:
    first_last: list[str] = []
    for text in page_texts:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        first_last.extend(lines[:2] + lines[-2:])
    threshold = max(3, round(len(page_texts) * 0.6))
    repeated = {line for line, count in Counter(first_last).items() if count >= threshold and len(line) < 160}
    return ["\n".join(line for line in text.splitlines() if line.strip() not in repeated) for text in page_texts]


def _sections(page_texts: list[str]) -> list[DissertationSection]:
    starts: list[tuple[SectionType, str, int]] = []
    for page_index, text in enumerate(page_texts, start=1):
        for line in text.splitlines():
            candidate = line.strip().strip(":.-")
            if not candidate or len(candidate) > 120:
                continue
            for section_type, pattern in HEADING_PATTERNS:
                if pattern.match(candidate) and all(existing[0] != section_type for existing in starts):
                    starts.append((section_type, candidate, page_index))
                    break
    starts.sort(key=lambda item: item[2])
    result: list[DissertationSection] = []
    for index, (section_type, title, start) in enumerate(starts):
        end = starts[index + 1][2] - 1 if index + 1 < len(starts) else len(page_texts)
        text = "\n".join(page_texts[start - 1 : end])
        result.append(
            DissertationSection(
                section_type=section_type,
                title=title,
                start_page=start,
                end_page=max(start, end),
                text=text,
                confidence=0.92,
            )
        )
    return result


def extract_pdf(filename: str, mime_type: str, data: bytes, settings: Settings) -> Dissertation:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DocumentRejected("PDF is malformed or unreadable") from exc
    if document.needs_pass:
        raise DocumentRejected("Encrypted PDFs are not accepted")
    if document.page_count > settings.max_pages:
        raise DocumentRejected("Document exceeds the 600-page limit")
    raw_texts: list[str] = []
    dimensions: list[tuple[float, float, float]] = []
    for page in document:
        text = page.get_text("text")
        raw_texts.append(text)
        image_area = 0.0
        for image in page.get_images(full=True):
            for rect in page.get_image_rects(image[0]):
                image_area += max(0, rect.width * rect.height)
        page_area = max(1, page.rect.width * page.rect.height)
        dimensions.append((page.rect.width, page.rect.height, min(1.0, image_area / page_area)))
    page_texts = _strip_repeated_margins(raw_texts)
    pages: list[DocumentPage] = []
    warnings: list[ExtractionWarning] = []
    for number, (text, (width, height, image_coverage)) in enumerate(zip(page_texts, dimensions, strict=True), start=1):
        readable = not (len(text.strip()) < 80 and image_coverage > 0.5)
        pages.append(DocumentPage(number=number, text=text, width=width, height=height, image_coverage=image_coverage, readable=readable, content_hash=_hash(text)))
        if not readable:
            warnings.append(ExtractionWarning(code="unreadable_page", message="Very little extractable text and high image coverage; visual inspection is required.", page=number, blocking=True))
    return Dissertation(filename=filename, mime_type=mime_type, sha256=hashlib.sha256(data).hexdigest(), pages=pages, sections=_sections(page_texts), warnings=warnings)


def extract_docx(filename: str, mime_type: str, data: bytes, settings: Settings) -> Dissertation:
    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:
        raise DocumentRejected("DOCX is malformed or unreadable") from exc
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    text = "\n".join(paragraphs)
    estimated_pages = max(1, (len(text) // 3000) + 1)
    if estimated_pages > settings.max_pages:
        raise DocumentRejected("Estimated document length exceeds the 600-page limit")
    # DOCX has no reliable page boundary. Keep one canonical text page and require
    # rendered-PDF conversion in production for authoritative page citations.
    warning = ExtractionWarning(code="docx_page_mapping", message="DOCX page citations are provisional until LibreOffice rendering and alignment complete.", blocking=True)
    page = DocumentPage(number=1, text=text, width=612, height=792, readable=bool(text.strip()), content_hash=_hash(text))
    if not text.strip():
        warning = ExtractionWarning(code="unreadable_document", message="No readable paragraph text was extracted.", page=1, blocking=True)
    return Dissertation(filename=filename, mime_type=mime_type, sha256=hashlib.sha256(data).hexdigest(), pages=[page], sections=_sections([text]), warnings=[warning])


def extract_legacy_doc(filename: str, mime_type: str, data: bytes, settings: Settings) -> Dissertation:
    text = _legacy_doc_text(data)
    estimated_pages = max(1, text.count("\f") + 1)
    if estimated_pages > settings.max_pages:
        raise DocumentRejected("Document exceeds the 600-page limit")
    warning = ExtractionWarning(
        code="legacy_doc_page_mapping",
        message="Legacy .doc text was extracted, but page citations are provisional until conversion to PDF.",
        blocking=True,
    )
    page = DocumentPage(
        number=1,
        text=text,
        width=612,
        height=792,
        readable=bool(text.strip()),
        content_hash=_hash(text),
    )
    return Dissertation(
        filename=filename,
        mime_type=mime_type,
        sha256=hashlib.sha256(data).hexdigest(),
        pages=[page],
        sections=_sections([text]),
        warnings=[warning],
    )


def extract_document(filename: str, mime_type: str, data: bytes, settings: Settings) -> Dissertation:
    if mime_type == "application/pdf":
        return extract_pdf(filename, mime_type, data, settings)
    if mime_type == "application/msword":
        return extract_legacy_doc(filename, mime_type, data, settings)
    return extract_docx(filename, mime_type, data, settings)

