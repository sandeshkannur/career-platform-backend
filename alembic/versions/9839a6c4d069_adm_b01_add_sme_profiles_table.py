"""adm_b01_add_sme_profiles_table

Revision ID: 9839a6c4d069
Revises: b2c3d4e5f6a1
Create Date: 2026-04-01 12:34:36.471350

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9839a6c4d069'
down_revision: Union[str, None] = 'b2c3d4e5f6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    ADM-B01: Create sme_profiles table for SME Registry CRUD.

    Weighting approach: Approach B (credentials × calibration composite).
    - credentials_score: computed from experience/seniority/education/sector inputs
    - calibration_score: set by aggregation service (ADM-B03) after each round
    - effective_weight:  never stored — always recomputed as credentials × calibration

    Deactivation: soft-delete only via status = 'inactive'. Rows are never hard-deleted.
    """
    op.create_table(
        "sme_profiles",
        sa.Column("id",                sa.Integer(),      nullable=False),
        sa.Column("full_name",         sa.String(200),    nullable=False),
        sa.Column("email",             sa.String(200),    nullable=False),
        sa.Column("career_assignments",sa.Text(),         nullable=True),
        sa.Column("years_experience",  sa.Integer(),      nullable=True),
        sa.Column("seniority_score",   sa.Float(),        nullable=True),
        sa.Column("education_score",   sa.Float(),        nullable=True),
        sa.Column("sector_relevance",  sa.Float(),        nullable=True),
        sa.Column("credentials_score", sa.Float(),        nullable=True),
        sa.Column("calibration_score", sa.Float(),        nullable=True),
        sa.Column("submission_count",  sa.Integer(),      nullable=False, server_default="0"),
        sa.Column("sector",            sa.String(200),    nullable=True),
        sa.Column("education",         sa.String(200),    nullable=True),
        sa.Column("status",            sa.String(20),     nullable=False, server_default="active"),
        sa.Column("created_at",        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_sme_profiles_email"),
    )
    op.create_index("ix_sme_profiles_id",     "sme_profiles", ["id"],     unique=False)
    op.create_index("ix_sme_profiles_email",  "sme_profiles", ["email"],  unique=True)
    op.create_index("ix_sme_profiles_status", "sme_profiles", ["status"], unique=False)


def downgrade() -> None:
    """Remove sme_profiles table (ADM-B01 rollback)."""
    op.drop_index("ix_sme_profiles_status", table_name="sme_profiles")
    op.drop_index("ix_sme_profiles_email",  table_name="sme_profiles")
    op.drop_index("ix_sme_profiles_id",     table_name="sme_profiles")
    op.drop_table("sme_profiles")
