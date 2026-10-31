"""Initial restricted-pilot schema."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_email", sa.String(320), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("rubric_version", sa.String(100), nullable=False),
        sa.Column("external_processing_authorized", sa.Boolean(), nullable=False),
        sa.Column("source_filename", sa.String(500)),
        sa.Column("source_key", sa.String(1000)),
        sa.Column("dissertation_json", sa.Text()),
        sa.Column("checks_json", sa.Text(), nullable=False),
        sa.Column("reviews_json", sa.Text(), nullable=False),
        sa.Column("checklist_json", sa.Text(), nullable=False),
        sa.Column("scores_json", sa.Text(), nullable=False),
        sa.Column("validation_json", sa.Text()),
        sa.Column("decisions_json", sa.Text(), nullable=False),
        sa.Column("artifacts_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assessments_owner_email", "assessments", ["owner_email"])
    op.create_index("ix_assessments_state", "assessments", ["state"])
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_email", sa.String(320), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_email", "key", name="uq_idempotency_owner_key"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("assessments.id")),
        sa.Column("owner_email", sa.String(320), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "deletion_tombstones",
        sa.Column("assessment_id", sa.String(36), primary_key=True),
        sa.Column("assessor_id", sa.String(320), nullable=False),
        sa.Column("deletion_event_id", sa.String(36), nullable=False, unique=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("deletion_tombstones")
    op.drop_table("audit_events")
    op.drop_table("idempotency_records")
    op.drop_table("assessments")
