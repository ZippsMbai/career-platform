"""add last_seen_at to jobs

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("last_seen_at", sa.DateTime(), nullable=True))
    # Backfill existing jobs so they don't look "never seen" — treat their
    # original creation time as the last time we saw them, which is accurate.
    op.execute("UPDATE jobs SET last_seen_at = created_at WHERE last_seen_at IS NULL")


def downgrade():
    op.drop_column("jobs", "last_seen_at")