"""pr42 add skill_aliases table

Revision ID: 8c612814971d
Revises: 650d8e341a0f
Create Date: 2026-02-07 01:16:06.059184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c612814971d'
down_revision: Union[str, None] = '650d8e341a0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "skill_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("assessment_version", sa.String(length=32), nullable=True),
        sa.Column("alias", sa.String(length=200), nullable=False),
        sa.Column("canonical_code", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    # Unique per (entity_type, assessment_version, alias) case-insensitive
    op.create_index(
        "ux_skill_aliases_entity_version_alias_ci",
        "skill_aliases",
        ["entity_type", "assessment_version", sa.text("lower(alias)")],
        unique=True,
    )

    # Helpful lookup index for canonical too (non-unique)
    op.create_index(
        "ix_skill_aliases_entity_version_canonical_ci",
        "skill_aliases",
        ["entity_type", "assessment_version", sa.text("lower(canonical_code)")],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_skill_aliases_entity_version_canonical_ci", table_name="skill_aliases")
    op.drop_index("ux_skill_aliases_entity_version_alias_ci", table_name="skill_aliases")
    op.drop_table("skill_aliases")
