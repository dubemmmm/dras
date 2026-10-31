import asyncio
from io import BytesIO

import fitz
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dras.config import Settings
from dras.db import Base
from dras.schemas import (
    ApprovalStatus,
    AssessmentCreate,
    ChecklistAnswer,
    Metadata,
    SectionReview,
)
from dras.service import AssessmentService


def synthetic_pdf() -> bytes:
    document = fitz.open()
    sections = [
        "ABSTRACT\nObjectives Methods Results Conclusion",
        "INTRODUCTION\nBackground and study objectives",
        "MATERIALS AND METHODS\nDesign setting sample analysis ethics",
        "RESULTS\nResults for each objective",
        "DISCUSSION\nInterpretation limitations future research",
        "CONCLUSION\nConclusion based on objectives",
        "REFERENCES\nAdams, A. (2020). Study.\nBrown, B. (2021). Study.",
        "APPENDICES\nEthical approval and questionnaire",
    ]
    for content in sections:
        page = document.new_page()
        page.insert_textbox(fitz.Rect(72, 72, 540, 720), content, fontsize=11)
    return document.tobytes()


def test_full_approval_and_deletion_flow(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'flow.db'}", storage_dir=tmp_path / "storage")
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    owner = "assessor@example.org"
    with Session(engine, expire_on_commit=False) as db:
        service = AssessmentService(db, settings)
        detail = service.create(owner, AssessmentCreate(metadata=Metadata(candidate_name="Pilot Candidate")), "create-1")
        listed = service.list(owner)
        assert len(listed) == 1
        assert listed[0].id == detail.id
        upload = UploadFile(filename="pilot.pdf", file=BytesIO(synthetic_pdf()), headers={"content-type": "application/pdf"})
        detail = asyncio.run(service.upload(detail.id, owner, detail.version, upload))
        source_name, source_data = service.source_bytes(detail.id, owner)
        assert source_name == "pilot.pdf"
        assert source_data.startswith(b"%PDF-")
        detail = service.extract(detail.id, owner, detail.version)
        assert detail.state == "extracted"
        assert detail.rendered_source_available
        assert service.rendered_source_bytes(detail.id, owner).startswith(b"%PDF-")
        detail = service.review(detail.id, owner, detail.version)
        for review in detail.reviews:
            detail = service.update_section(detail.id, owner, detail.version, review.section, {"assessor_comment": f"Approved {review.section.value}.", "approval_status": ApprovalStatus.APPROVED})
        checklist_updates = [{"number": item.number, "approved_answer": ChecklistAnswer.NO if item.number == 8 else ChecklistAnswer.YES, "assessor_note": "Confirmed", "approved": True} for item in detail.checklist]
        detail = service.update_checklist(detail.id, owner, detail.version, {"items": checklist_updates})
        score_updates = [{"criterion": score.criterion, "approved": score.maximum, "justification": "Confirmed", "status": ApprovalStatus.APPROVED} for score in detail.scores]
        detail = service.update_scores(detail.id, owner, detail.version, {"scores": score_updates})
        detail = service.update_decisions(detail.id, owner, detail.version, {"publishable": True, "publishability_approved": True, "award_adequacy_confirmed": True, "general_comments": "Approved for pilot export."})
        detail = service.validate(detail.id, owner, detail.version)
        assert detail.validation.valid
        detail = service.finalize(detail.id, owner, detail.version)
        assert {item["name"] for item in service.artifacts(detail.id, owner)} == {"assessment_report.docx", "confidential_scoring_report.docx", "internal_evidence_report.json"}
        service.delete(detail.id, owner, detail.version)
        assert not (settings.storage_dir / str(detail.id)).exists()
        assert db.execute(__import__("sqlalchemy").text("select count(*) from deletion_tombstones")).scalar_one() == 1


def test_authorized_assessment_runs_structured_review(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'authorized.db'}",
        storage_dir=tmp_path / "storage",
        openai_api_key="test-only-key",
    )
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    calls = []

    class FakeProvider:
        def __init__(self, provider_settings):
            assert provider_settings.openai_api_key == "test-only-key"

        def structured(self, *, model, prompt, schema):
            calls.append((model, prompt, schema))
            return (
                SectionReview(
                    section="abstract",
                    proposed_comment="Evidence-backed automated review.",
                ),
                {"request_id": "test"},
            )

    monkeypatch.setattr("dras.service.OpenAIResponsesProvider", FakeProvider)
    owner = "assessor@example.org"
    with Session(engine, expire_on_commit=False) as db:
        assessment_service = AssessmentService(db, settings)
        detail = assessment_service.create(
            owner,
            AssessmentCreate(metadata=Metadata(candidate_name="Pilot Candidate")),
            "authorized-create",
        )
        upload = UploadFile(
            filename="pilot.pdf",
            file=BytesIO(synthetic_pdf()),
            headers={"content-type": "application/pdf"},
        )
        detail = asyncio.run(
            assessment_service.upload(detail.id, owner, detail.version, upload)
        )
        detail = assessment_service.extract(detail.id, owner, detail.version)
        detail = assessment_service.update_processing_authorization(
            detail.id,
            owner,
            detail.version,
            True,
        )
        detail = assessment_service.review(detail.id, owner, detail.version)

    assert detail.external_processing_authorized
    assert calls
    assert all(review.proposed_comment == "Evidence-backed automated review." for review in detail.reviews)

