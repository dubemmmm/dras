from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AssessmentState(StrEnum):
    DRAFT = "draft"
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    REVIEWING = "reviewing"
    AWAITING_APPROVAL = "awaiting_approval"
    VALIDATING = "validating"
    FINALIZING = "finalizing"
    FINALIZED = "finalized"
    FAILED = "failed"
    DELETED = "deleted"


class SectionType(StrEnum):
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    LITERATURE_REVIEW = "literature_review"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    REFERENCES = "references"
    APPENDICES = "appendices"
    GENERAL_PRESENTATION = "general_presentation"


class CheckStatus(StrEnum):
    VERIFIED_PASS = "verified_pass"
    VERIFIED_FAIL = "verified_fail"
    CANNOT_VERIFY = "cannot_verify"
    NOT_APPLICABLE = "not_applicable"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ChecklistAnswer(StrEnum):
    YES = "Yes"
    NO = "No"
    CANNOT_ANSWER = "Cannot answer"


class Metadata(StrictModel):
    candidate_name: str | None = None
    registration_number: str | None = None
    dissertation_title: str | None = None
    supervisor_name: str | None = None
    assessor_name: str | None = None
    assessor_email: str | None = None
    assessment_date: date | None = None


class MetadataExtraction(StrictModel):
    metadata: Metadata
    confidence: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AssessmentCreate(StrictModel):
    metadata: Metadata = Field(default_factory=Metadata)
    rubric_version: str = "wapcp-2026-draft-v1"
    external_processing_authorized: bool = False


class EvidenceReference(StrictModel):
    page: int
    excerpt: str
    bbox: tuple[float, float, float, float] | None = None
    content_hash: str


class ReviewFinding(StrictModel):
    id: str
    section: SectionType
    criterion: str
    description: str
    significance: str
    recommendation: str
    severity: str
    confidence: float = Field(ge=0, le=1)
    verification_status: str
    evidence: list[EvidenceReference] = Field(default_factory=list)
    assessor_edit: str | None = None
    approval_status: ApprovalStatus = ApprovalStatus.PENDING


class DocumentPage(StrictModel):
    number: int
    text: str
    width: float
    height: float
    image_coverage: float = 0
    readable: bool = True
    content_hash: str


class DissertationSection(StrictModel):
    section_type: SectionType
    title: str
    start_page: int
    end_page: int
    text: str
    confidence: float = Field(ge=0, le=1)


class ExtractionWarning(StrictModel):
    code: str
    message: str
    page: int | None = None
    blocking: bool = False
    resolved: bool = False
    resolution_note: str | None = None


class Dissertation(StrictModel):
    filename: str
    mime_type: str
    sha256: str
    pages: list[DocumentPage]
    sections: list[DissertationSection]
    warnings: list[ExtractionWarning] = Field(default_factory=list)


class DeterministicCheck(StrictModel):
    code: str
    version: str = "1.0.0"
    status: CheckStatus
    explanation: str
    evidence: list[EvidenceReference] = Field(default_factory=list)


class SectionReview(StrictModel):
    section: SectionType
    proposed_comment: str = ""
    assessor_comment: str | None = None
    findings: list[ReviewFinding] = Field(default_factory=list)
    approval_status: ApprovalStatus = ApprovalStatus.PENDING


class ChecklistResponse(StrictModel):
    number: int = Field(ge=1, le=13)
    question: str
    proposed_answer: ChecklistAnswer = ChecklistAnswer.CANNOT_ANSWER
    justification: str = ""
    evidence: list[EvidenceReference] = Field(default_factory=list)
    human_attestation_required: bool = False
    approved_answer: ChecklistAnswer | None = None
    assessor_note: str | None = None
    approved: bool = False


class Score(StrictModel):
    criterion: str
    maximum: int
    proposed: int | None = None
    approved: int | None = None
    justification: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING

    @model_validator(mode="after")
    def score_within_range(self) -> Score:
        for value in (self.proposed, self.approved):
            if value is not None and not 0 <= value <= self.maximum:
                raise ValueError(f"score must be between 0 and {self.maximum}")
        return self


class ValidationIssue(StrictModel):
    code: str
    message: str
    blocking: bool = True


class ValidationResult(StrictModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class FinalDecisions(StrictModel):
    publishable: bool | None = None
    publishability_approved: bool = False
    award_adequacy_confirmed: bool = False
    general_comments: str = ""


class AssessmentView(StrictModel):
    id: UUID
    owner_email: str
    state: AssessmentState
    version: int
    metadata: Metadata
    rubric_version: str
    external_processing_authorized: bool
    source_filename: str | None = None
    created_at: datetime
    updated_at: datetime


class AssessmentDetail(AssessmentView):
    dissertation: Dissertation | None = None
    checks: list[DeterministicCheck] = Field(default_factory=list)
    reviews: list[SectionReview] = Field(default_factory=list)
    checklist: list[ChecklistResponse] = Field(default_factory=list)
    scores: list[Score] = Field(default_factory=list)
    validation: ValidationResult | None = None
    decisions: FinalDecisions = Field(default_factory=FinalDecisions)
    rendered_source_available: bool = False


class MutationEnvelope(StrictModel):
    expected_version: int = Field(ge=1)
    data: dict[str, Any] = Field(default_factory=dict)

