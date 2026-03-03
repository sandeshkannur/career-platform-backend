"""convert recommended_careers to jsonb and add skill_tiers"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic.
revision = "3e8a4b9f2d31"
down_revision = "f66212d1b2fa"  # <- your current head per screenshot
branch_labels = None
depends_on = None


def upgrade():
    # 1) Add skill_tiers as JSONB (nullable)
    op.add_column(
        "assessment_results",
        sa.Column("skill_tiers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # 2) Convert recommended_careers (TEXT/VARCHAR) -> JSONB in place.
    #    Handles:
    #      - NULL or '' -> NULL
    #      - Already JSON text ([...] or {...}) -> cast to jsonb
    #      - Comma-separated text -> JSON array
    op.alter_column(
        "assessment_results",
        "recommended_careers",
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="""
            CASE
              WHEN recommended_careers IS NULL OR btrim(recommended_careers) = ''
                THEN NULL
              WHEN btrim(recommended_careers) ~ '^(\\[.*\\]|\\{.*\\})$'
                THEN recommended_careers::jsonb
              ELSE to_jsonb(regexp_split_to_array(btrim(recommended_careers), '\\s*,\\s*'))
            END
        """,
        existing_nullable=True,
    )


def downgrade():
    # 1) Convert recommended_careers JSONB back to TEXT
    op.alter_column(
        "assessment_results",
        "recommended_careers",
        type_=sa.Text(),
        postgresql_using="""
            CASE
              WHEN recommended_careers IS NULL THEN NULL
              ELSE recommended_careers::text
            END
        """,
        existing_nullable=True,
    )

    # 2) Drop skill_tiers
    op.drop_column("assessment_results", "skill_tiers")
