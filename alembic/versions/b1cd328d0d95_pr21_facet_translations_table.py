"""PR21 facet translations table

Revision ID: b1cd328d0d95
Revises: 870d6eef49cd
Create Date: 2026-02-15 22:52:54.511583

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1cd328d0d95'
down_revision: Union[str, None] = '870d6eef49cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- PR21: facet_translations (additive; FK to aq_facets.facet_id) ---
    op.create_table(
        "facet_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("facet_id", sa.String(length=120), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("facet_name", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["facet_id"], ["aq_facets.facet_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["locale"], ["languages.code"], ondelete="RESTRICT"),
        sa.UniqueConstraint("facet_id", "locale", name="uq_ft_facet_locale"),
    )
    op.create_index("ix_ft_facet_id", "facet_translations", ["facet_id"])
    op.create_index("ix_ft_locale", "facet_translations", ["locale"])


def downgrade() -> None:
    op.drop_index("ix_ft_locale", table_name="facet_translations")
    op.drop_index("ix_ft_facet_id", table_name="facet_translations")
    op.drop_table("facet_translations")
