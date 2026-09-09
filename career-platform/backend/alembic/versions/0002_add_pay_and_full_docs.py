"""add pay_text to jobs, cover_letter_full and tailored_resume to analyses

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("pay_text", sa.String(), nullable=True))
    op.add_column("analyses", sa.Column("cover_letter_full", sa.Text(), nullable=True))
    op.add_column("analyses", sa.Column("tailored_resume", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("analyses", "tailored_resume")
    op.drop_column("analyses", "cover_letter_full")
    op.drop_column("jobs", "pay_text")
