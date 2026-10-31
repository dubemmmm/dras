from io import BytesIO

import fitz
import pytest
from docx import Document

from dras.checks import run_checks
from dras.config import Settings
from dras.constants import CHECKLIST_QUESTIONS, SCORE_MAXIMA
from dras.extraction import DocumentRejected, extract_document, extract_metadata_from_text, validate_upload
from dras.reports import build_assessment_report, build_scoring_report
from dras.schemas import (
    ApprovalStatus,
    AssessmentDetail,
    AssessmentState,
    ChecklistAnswer,
    Metadata,
    FinalDecisions,
    Score,
    SectionReview,
    SectionType,
)


def pdf_bytes(lines: list[str]) -> bytes:
    document = fitz.open()
    for text in lines:
        page = document.new_page()
        page.insert_textbox(fitz.Rect(72, 72, 540, 720), text, fontsize=11)
    return document.tobytes()


@pytest.fixture
def settings(tmp_path):
    return Settings(storage_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'test.db'}")


def test_exact_institutional_contract():
    assert len(CHECKLIST_QUESTIONS) == 13
    assert CHECKLIST_QUESTIONS[7] == "Were Results repeated under Discussion?"
    assert sum(SCORE_MAXIMA.values()) == 60
    assert Score(criterion="Methods", maximum=10, approved=10).approved == 10
    with pytest.raises(ValueError):
        Score(criterion="Methods", maximum=10, approved=11)


def test_upload_signature_and_macro_protection(settings):
    with pytest.raises(DocumentRejected, match="signature"):
        validate_upload("fake.pdf", "application/pdf", b"not a pdf", settings)
    doc = Document()
    doc.add_paragraph("Methods")
    stream = BytesIO()
    doc.save(stream)
    assert "wordprocessingml" in validate_upload("valid.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", stream.getvalue(), settings)


def test_title_page_metadata_extraction_matches_legacy_sample():
    title_page = """WEST AFRICAN POSTGRADUATE COLLEGE OF PHARMACISTS FACULTY OF CLINICAL PHARMACY

MEDICATION ADHERENCE AMONG HIV-POSITIVE PATIENTS ATTENDING HIV CLINIC AT YILO KROBO GOVERNMENT HOSPITAL, GHANA
BY
BOAKYE ANSONG
(20257289)
INFECTIOUS DISEASE SPECIALITY
SUPERVISOR:
PHARM DR. SETH TWUM
EASTERN REGIONAL HOSPITAL, KOFORIDUA
"""
    result = extract_metadata_from_text(title_page)
    assert result.metadata.candidate_name == "BOAKYE ANSONG"
    assert result.metadata.registration_number == "20257289"
    assert result.metadata.supervisor_name == "PHARM DR. SETH TWUM"
    assert result.metadata.dissertation_title == "MEDICATION ADHERENCE AMONG HIV-POSITIVE PATIENTS ATTENDING HIV CLINIC AT YILO KROBO GOVERNMENT HOSPITAL, GHANA"
    assert not result.warnings


def test_pdf_extraction_sections_headers_and_checks(settings):
    data = pdf_bytes([
        "CONFIDENTIAL HEADER\nABSTRACT\nObjectives Methods Results Conclusion\nCONFIDENTIAL FOOTER",
        "CONFIDENTIAL HEADER\nINTRODUCTION\nBackground and objectives\nCONFIDENTIAL FOOTER",
        "CONFIDENTIAL HEADER\nMATERIALS AND METHODS\nStudy design and ethical approval\nCONFIDENTIAL FOOTER",
        "CONFIDENTIAL HEADER\nRESULTS\nA total of 100 participants\nCONFIDENTIAL FOOTER",
        "CONFIDENTIAL HEADER\nDISCUSSION\nInterpretation and limitations\nCONFIDENTIAL FOOTER",
        "CONFIDENTIAL HEADER\nCONCLUSION\nConclusions follow objectives\nCONFIDENTIAL FOOTER",
        "CONFIDENTIAL HEADER\nREFERENCES\nAdams, A. (2020) Example.\nBrown, B. (2021) Example.\nCONFIDENTIAL FOOTER",
        "CONFIDENTIAL HEADER\nAPPENDICES\nEthical approval letter\nCONFIDENTIAL FOOTER",
    ])
    validate_upload("study.pdf", "application/pdf", data, settings)
    dissertation = extract_document("study.pdf", "application/pdf", data, settings)
    types = {section.section_type for section in dissertation.sections}
    assert SectionType.METHODS in types
    assert SectionType.APPENDICES in types
    assert "CONFIDENTIAL HEADER" not in dissertation.pages[0].text
    checks = {check.code: check.status for check in run_checks(dissertation)}
    assert checks["abstract.required_subheadings"] == "verified_pass"
    assert checks["appendix.ethics_presence"] == "verified_pass"


def make_approved_detail():
    from datetime import datetime, timezone
    from uuid import uuid4
    from dras.constants import initial_checklist, initial_scores

    checklist = initial_checklist()
    for item in checklist:
        item.approved_answer = ChecklistAnswer.NO if item.number == 8 else ChecklistAnswer.YES
        item.approved = True
        item.assessor_note = "Assessor confirmed."
    scores = initial_scores()
    for score in scores:
        score.approved = score.maximum
        score.status = ApprovalStatus.APPROVED
        score.justification = "Approved against the pilot rubric."
    reviews = [SectionReview(section=section, proposed_comment=f"Approved {section.value} comment.", assessor_comment=f"Assessor comment for {section.value}.", approval_status=ApprovalStatus.APPROVED) for section in SectionType]
    now = datetime.now(timezone.utc)
    return AssessmentDetail(id=uuid4(), owner_email="assessor@example.org", state=AssessmentState.FINALIZED, version=10, metadata=Metadata(candidate_name="Ada Example", registration_number="P-001", dissertation_title="Synthetic Study", assessor_name="Dr Reviewer", assessor_email="assessor@example.org"), rubric_version="wapcp-2026-draft-v1", external_processing_authorized=True, created_at=now, updated_at=now, reviews=reviews, checklist=checklist, scores=scores, decisions=FinalDecisions(publishable=True, publishability_approved=True, award_adequacy_confirmed=True))


def test_report_confidentiality_and_literature_exclusion():
    detail = make_approved_detail()
    student = build_assessment_report(detail)
    scoring = build_scoring_report(detail)
    student_doc = Document(BytesIO(student))
    student_text = "\n".join(p.text for p in student_doc.paragraphs)
    score_doc = Document(BytesIO(scoring))
    score_text = "\n".join(p.text for p in score_doc.paragraphs) + "\n" + "\n".join(cell.text for table in score_doc.tables for row in table.rows for cell in row.cells)
    assert "Assessor comment for literature_review" not in student_text
    assert "Total Score" in score_text
    assert "CONFIDENTIAL" in score_text

