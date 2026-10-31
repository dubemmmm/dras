from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from dras.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssessmentRecord(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    state: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    rubric_version: Mapped[str] = mapped_column(String(100), default="wapcp-2026-draft-v1")
    external_processing_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    source_filename: Mapped[str | None] = mapped_column(String(500))
    source_key: Mapped[str | None] = mapped_column(String(1000))
    rendered_source_key: Mapped[str | None] = mapped_column(String(1000))
    dissertation_json: Mapped[str | None] = mapped_column(Text)
    checks_json: Mapped[str] = mapped_column(Text, default="[]")
    reviews_json: Mapped[str] = mapped_column(Text, default="[]")
    checklist_json: Mapped[str] = mapped_column(Text, default="[]")
    scores_json: Mapped[str] = mapped_column(Text, default="[]")
    validation_json: Mapped[str | None] = mapped_column(Text)
    decisions_json: Mapped[str] = mapped_column(Text, default="{}")
    artifacts_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("owner_email", "key", name="uq_idempotency_owner_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("assessments.id"))
    owner_email: Mapped[str] = mapped_column(String(320), index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeletionTombstone(Base):
    __tablename__ = "deletion_tombstones"

    assessment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assessor_id: Mapped[str] = mapped_column(String(320), index=True)
    deletion_event_id: Mapped[str] = mapped_column(String(36), unique=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

