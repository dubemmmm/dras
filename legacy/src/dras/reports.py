from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from typing import Any

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from dras.schemas import AssessmentDetail, SectionType

BLUE = RGBColor(31, 77, 120)
LIGHT_BLUE = "E8EEF5"


def _set_repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    element = OxmlElement("w:tblHeader")
    element.set(qn("w:val"), "true")
    tr_pr.append(element)


def _shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    tc_pr.append(shading)


def _configure(doc: Document, confidential: bool = False) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = section.bottom_margin = Inches(1)
    section.left_margin = section.right_margin = Inches(1)
    section.header_distance = section.footer_distance = Inches(0.492)
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.1
    for style_name, size, before, after in (("Title", 22, 0, 8), ("Heading 1", 16, 16, 8), ("Heading 2", 13, 12, 6)):
        style = doc.styles[style_name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.color.rgb = BLUE
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
    header = section.header.paragraphs[0]
    header.text = "WAPCP Dissertation Assessment | Restricted pilot"
    header.style = doc.styles["Normal"]
    header.runs[0].font.size = Pt(9)
    header.runs[0].font.color.rgb = RGBColor(100, 100, 100)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run("CONFIDENTIAL — assessor only" if confidential else "Assessor-approved student-facing report").font.size = Pt(9)


def _title(doc: Document, subtitle: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("WEST AFRICAN POSTGRADUATE COLLEGE OF PHARMACISTS")
    run.bold = True
    run.font.size = Pt(13)
    run.font.color.rgb = BLUE
    paragraph = doc.add_paragraph(style="Title")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.add_run(subtitle)


def _metadata(doc: Document, assessment: AssessmentDetail) -> None:
    metadata = assessment.metadata
    values = (
        ("Name of Candidate", metadata.candidate_name),
        ("Registration Number", metadata.registration_number),
        ("Title of Dissertation", metadata.dissertation_title),
        ("Dissertation Supervisor", metadata.supervisor_name),
    )
    for label, value in values:
        paragraph = doc.add_paragraph()
        paragraph.add_run(f"{label}: ").bold = True
        paragraph.add_run(value or "Not supplied")


def _table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    table.style = "Table Grid"
    for index, (header, width) in enumerate(zip(headers, widths, strict=True)):
        cell = table.rows[0].cells[index]
        cell.width = Inches(width)
        cell.text = header
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        _shade(cell, LIGHT_BLUE)
        for run in cell.paragraphs[0].runs:
            run.bold = True
    _set_repeat_header(table.rows[0])
    for row_values in rows:
        cells = table.add_row().cells
        for index, (value, width) in enumerate(zip(row_values, widths, strict=True)):
            cells[index].width = Inches(width)
            cells[index].text = value
            cells[index].vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def build_assessment_report(assessment: AssessmentDetail) -> bytes:
    doc = Document()
    _configure(doc)
    _title(doc, "ASSESSMENT OF DISSERTATION REPORT")
    _metadata(doc, assessment)
    doc.add_heading("Assessment checklist", level=1)
    checklist_rows = []
    for item in assessment.checklist:
        checklist_rows.append([str(item.number), item.question, item.approved_answer.value if item.approved_answer else "Pending", item.assessor_note or item.justification])
    _table(doc, ["S/N", "Item to be assessed", "Response", "Comments"], checklist_rows, [0.45, 3.4, 0.85, 1.8])
    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_heading("Detailed assessment report", level=1)
    doc.add_paragraph("This section is provided to the student to improve the quality of the dissertation.")
    excluded = {SectionType.LITERATURE_REVIEW}
    for review in assessment.reviews:
        if review.section in excluded:
            continue
        doc.add_heading(review.section.value.replace("_", " ").title(), level=2)
        doc.add_paragraph(review.assessor_comment or review.proposed_comment or "No approved comment supplied.")
    doc.add_heading("Publishability", level=2)
    doc.add_paragraph("Yes" if assessment.decisions.publishable else "No" if assessment.decisions.publishable is False else "Pending assessor decision")
    doc.add_heading("General comments", level=2)
    doc.add_paragraph(assessment.decisions.general_comments or "No general comments supplied.")
    doc.add_paragraph("Restricted pilot output. Academic reliability has not yet been formally validated.")
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def build_scoring_report(assessment: AssessmentDetail) -> bytes:
    doc = Document()
    _configure(doc, confidential=True)
    _title(doc, "CONFIDENTIAL SCORING OF DISSERTATION")
    paragraph = doc.add_paragraph("This report is confidential and must not be made available to the student.")
    paragraph.runs[0].bold = True
    _metadata(doc, assessment)
    rows = [[str(index), score.criterion, str(score.maximum), str(score.approved) if score.approved is not None else "Pending"] for index, score in enumerate(assessment.scores, start=1)]
    approved = [score.approved for score in assessment.scores]
    total = str(sum(value for value in approved if value is not None)) if all(value is not None for value in approved) else "Pending"
    rows.extend([["", "Oral Defence", "—", "—"], ["", "Total Score", "60", total]])
    _table(doc, ["S/N", "Item", "Maximum", "Actual"], rows, [0.55, 3.65, 1.0, 1.3])
    doc.add_paragraph(f"Name of Assessor: {assessment.metadata.assessor_name or 'Not supplied'}")
    doc.add_paragraph(f"Email Address: {assessment.metadata.assessor_email or 'Not supplied'}")
    doc.add_paragraph("Signature: __________________________________  Date: __________________")
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def build_evidence_json(assessment: AssessmentDetail) -> bytes:
    payload: dict[str, Any] = assessment.model_dump(mode="json")
    payload["notice"] = "Restricted pilot; not a validated production examiner."
    return json.dumps(payload, indent=2, ensure_ascii=False).encode()


def convert_docx_to_pdf(docx_bytes: bytes) -> bytes | None:
    """Convert through LibreOffice and reject empty/malformed output."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    with tempfile.TemporaryDirectory(prefix="dras-report-") as folder:
        source = os.path.join(folder, "report.docx")
        profile = os.path.join(folder, "profile")
        with open(source, "wb") as handle:
            handle.write(docx_bytes)
        result = subprocess.run(
            [soffice, "--headless", f"-env:UserInstallation=file://{profile}", "--convert-to", "pdf", "--outdir", folder, source],
            capture_output=True,
            timeout=120,
            check=False,
        )
        target = os.path.join(folder, "report.pdf")
        if result.returncode or not os.path.exists(target) or os.path.getsize(target) < 500:
            raise RuntimeError("Report PDF conversion failed")
        with open(target, "rb") as handle:
            payload = handle.read()
        pdf = __import__("fitz").open(stream=payload, filetype="pdf")
        if pdf.page_count < 1 or not any(page.get_text().strip() for page in pdf):
            raise RuntimeError("Rendered report PDF is blank")
        return payload

