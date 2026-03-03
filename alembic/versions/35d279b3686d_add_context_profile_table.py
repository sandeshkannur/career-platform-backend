"""add context_profile table

Revision ID: 35d279b3686d
Revises: 6d561fe21dcd
Create Date: 2026-01-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "35d279b3686d"
down_revision = "6d561fe21dcd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "context_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("assessment_version", sa.String(length=32), nullable=False),
        sa.Column("scoring_config_version", sa.String(length=32), nullable=False),
        sa.Column("ses_band", sa.String(length=32), nullable=False),
        sa.Column("education_board", sa.String(length=32), nullable=False),
        sa.Column("support_level", sa.String(length=32), nullable=False),
        sa.Column("resource_access", sa.String(length=32), nullable=True),
        sa.Column("cps_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            ondelete="CASCADE",
            name="fk_context_profile_assessment_id",
        ),
        sa.ForeignKeyConstraint(
            ["student_id"],
            ["students.id"],
            ondelete="CASCADE",
            name="fk_context_profile_student_id",
        ),
        sa.UniqueConstraint("assessment_id", name="uq_context_profile_assessment_id"),
    )

    op.create_index("ix_context_profile_assessment_id", "context_profile", ["assessment_id"])
    op.create_index("ix_context_profile_student_id", "context_profile", ["student_id"])
    op.create_index("ix_context_profile_assessment_version", "context_profile", ["assessment_version"])
    op.create_index("ix_context_profile_scoring_config_version", "context_profile", ["scoring_config_version"])
    op.create_index(
        "ix_context_profile_student_version",
        "context_profile",
        ["student_id", "scoring_config_version"],
    )

    # Remove the temporary default after table creation to keep the schema clean.
    op.alter_column("context_profile", "cps_score", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_context_profile_student_version", table_name="context_profile")
    op.drop_index("ix_context_profile_scoring_config_version", table_name="context_profile")
    op.drop_index("ix_context_profile_assessment_version", table_name="context_profile")
    op.drop_index("ix_context_profile_student_id", table_name="context_profile")
    op.drop_index("ix_context_profile_assessment_id", table_name="context_profile")
    op.drop_table("context_profile")
