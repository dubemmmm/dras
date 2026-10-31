"""Add private rendered-source PDF key."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.add_column("assessments", sa.Column("rendered_source_key", sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column("assessments", "rendered_source_key")
