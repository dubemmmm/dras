from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from dras.config import Settings, get_settings
from dras.db import create_schema, get_db
from dras.schemas import AssessmentCreate, AssessmentDetail, AssessmentView, MetadataExtraction, MutationEnvelope, SectionType
from dras.service import AssessmentService


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    yield


app = FastAPI(title="DRAS Private API", version="1.0.0", lifespan=lifespan, docs_url=None, redoc_url=None)


def identity(
    x_service_token: str = Header(...),
    x_assessor_email: str = Header(...),
    settings: Settings = Depends(get_settings),
) -> str:
    email = x_assessor_email.strip().lower()
    if x_service_token != settings.service_token:
        raise HTTPException(status_code=401, detail="Invalid private service credential")
    if email not in settings.allowed_assessors:
        raise HTTPException(status_code=403, detail="Assessor is not allowlisted")
    return email


def service(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> AssessmentService:
    return AssessmentService(db, settings)


@app.get("/health/live")
def live() -> dict:
    return {"status": "live"}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/v1/config/processing")
def processing_config(
    owner: str = Depends(identity),
    settings: Settings = Depends(get_settings),
) -> dict:
    return {
        "openai_configured": bool(settings.openai_api_key),
        "review_model": settings.review_model,
        "response_storage": False,
    }


@app.post("/v1/metadata/extract", response_model=MetadataExtraction)
async def preview_metadata(source: UploadFile = File(...), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return await svc.preview_metadata(source)


@app.post("/v1/assessments", response_model=AssessmentDetail, status_code=201)
def create_assessment(body: AssessmentCreate, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.create(owner, body, idempotency_key)


@app.get("/v1/assessments", response_model=list[AssessmentView])
def list_assessments(owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.list(owner)


@app.get("/v1/assessments/{assessment_id}", response_model=AssessmentDetail)
def get_assessment(assessment_id: UUID, owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.get(assessment_id, owner)


@app.post("/v1/assessments/{assessment_id}/source", response_model=AssessmentDetail)
async def upload_source(assessment_id: UUID, source: UploadFile = File(...), expected_version: int = Header(..., alias="Expected-Version"), idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return await svc.upload(assessment_id, owner, expected_version, source)


@app.post("/v1/assessments/{assessment_id}/extract", response_model=AssessmentDetail)
def extract(assessment_id: UUID, body: MutationEnvelope, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.extract(assessment_id, owner, body.expected_version)


@app.post("/v1/assessments/{assessment_id}/review", response_model=AssessmentDetail)
def review(assessment_id: UUID, body: MutationEnvelope, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.review(assessment_id, owner, body.expected_version)


@app.get("/v1/assessments/{assessment_id}/status", response_model=AssessmentDetail)
def status(assessment_id: UUID, owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.get(assessment_id, owner)


@app.get("/v1/assessments/{assessment_id}/source")
def download_source(assessment_id: UUID, owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    filename, data = svc.source_bytes(assessment_id, owner)
    media = (
        "application/pdf"
        if filename.lower().endswith(".pdf")
        else "application/msword"
        if filename.lower().endswith(".doc")
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/v1/assessments/{assessment_id}/source/rendered")
def rendered_source(assessment_id: UUID, owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    data = svc.rendered_source_bytes(assessment_id, owner)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="rendered-source.pdf"'})


@app.post("/v1/assessments/{assessment_id}/source/render", response_model=AssessmentDetail)
def render_source(assessment_id: UUID, body: MutationEnvelope, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.render_source(assessment_id, owner, body.expected_version)


@app.patch("/v1/assessments/{assessment_id}/processing", response_model=AssessmentDetail)
def patch_processing(
    assessment_id: UUID,
    body: MutationEnvelope,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    owner: str = Depends(identity),
    svc: AssessmentService = Depends(service),
):
    return svc.update_processing_authorization(
        assessment_id,
        owner,
        body.expected_version,
        bool(body.data.get("authorized", False)),
    )


@app.patch("/v1/assessments/{assessment_id}/warnings", response_model=AssessmentDetail)
def patch_warnings(assessment_id: UUID, body: MutationEnvelope, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.update_warnings(assessment_id, owner, body.expected_version, body.data)


@app.get("/v1/assessments/{assessment_id}/sections/{section}")
def get_section(assessment_id: UUID, section: SectionType, owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    detail = svc.get(assessment_id, owner)
    return next((item for item in detail.reviews if item.section == section), {"section": section, "findings": []})


@app.patch("/v1/assessments/{assessment_id}/sections/{section}", response_model=AssessmentDetail)
def patch_section(assessment_id: UUID, section: SectionType, body: MutationEnvelope, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.update_section(assessment_id, owner, body.expected_version, section, body.data)


@app.get("/v1/assessments/{assessment_id}/checklist")
def get_checklist(assessment_id: UUID, owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.get(assessment_id, owner).checklist


@app.patch("/v1/assessments/{assessment_id}/checklist", response_model=AssessmentDetail)
def patch_checklist(assessment_id: UUID, body: MutationEnvelope, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.update_checklist(assessment_id, owner, body.expected_version, body.data)


@app.get("/v1/assessments/{assessment_id}/scores")
def get_scores(assessment_id: UUID, owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.get(assessment_id, owner).scores


@app.patch("/v1/assessments/{assessment_id}/scores", response_model=AssessmentDetail)
def patch_scores(assessment_id: UUID, body: MutationEnvelope, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.update_scores(assessment_id, owner, body.expected_version, body.data)


@app.patch("/v1/assessments/{assessment_id}/decisions", response_model=AssessmentDetail)
def patch_decisions(assessment_id: UUID, body: MutationEnvelope, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.update_decisions(assessment_id, owner, body.expected_version, body.data)


@app.post("/v1/assessments/{assessment_id}/validate", response_model=AssessmentDetail)
def validate(assessment_id: UUID, body: MutationEnvelope, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.validate(assessment_id, owner, body.expected_version)


@app.post("/v1/assessments/{assessment_id}/finalize", response_model=AssessmentDetail)
def finalize(assessment_id: UUID, body: MutationEnvelope, idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.finalize(assessment_id, owner, body.expected_version)


@app.get("/v1/assessments/{assessment_id}/artifacts")
def artifacts(assessment_id: UUID, owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    return svc.artifacts(assessment_id, owner)


@app.get("/v1/assessments/{assessment_id}/artifacts/{name}")
def download_artifact(assessment_id: UUID, name: str, owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    data = svc.artifact_bytes(assessment_id, owner, name)
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if name.endswith(".docx") else "application/pdf" if name.endswith(".pdf") else "application/json"
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.delete("/v1/assessments/{assessment_id}", status_code=204)
def delete_assessment(assessment_id: UUID, expected_version: int = Header(..., alias="Expected-Version"), idempotency_key: str = Header(..., alias="Idempotency-Key"), owner: str = Depends(identity), svc: AssessmentService = Depends(service)):
    svc.delete(assessment_id, owner, expected_version)
    return Response(status_code=204)

