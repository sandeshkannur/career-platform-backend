"""add extended fields to sme_profiles

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-04-10

Adds missing columns to sme_profiles:
  phone, organization, designation, expertise_domain, max_careers, notes
"""
from alembic import op
import sqlalchemy as sa

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sme_profiles", sa.Column("phone",            sa.String(50),  nullable=True))
    op.add_column("sme_profiles", sa.Column("organization",     sa.String(200), nullable=True))
    op.add_column("sme_profiles", sa.Column("designation",      sa.String(200), nullable=True))
    op.add_column("sme_profiles", sa.Column("expertise_domain", sa.String(100), nullable=True))
    op.add_column("sme_profiles", sa.Column("max_careers",      sa.Integer(),   nullable=False, server_default="3"))
    op.add_column("sme_profiles", sa.Column("notes",            sa.Text(),      nullable=True))
    op.create_index("ix_sme_profiles_expertise_domain", "sme_profiles", ["expertise_domain"])


def downgrade() -> None:
    op.drop_index("ix_sme_profiles_expertise_domain", table_name="sme_profiles")
    op.drop_column("sme_profiles", "notes")
    op.drop_column("sme_profiles", "max_careers")
    op.drop_column("sme_profiles", "expertise_domain")
    op.drop_column("sme_profiles", "designation")
    op.drop_column("sme_profiles", "organization")
    op.drop_column("sme_profiles", "phone")
