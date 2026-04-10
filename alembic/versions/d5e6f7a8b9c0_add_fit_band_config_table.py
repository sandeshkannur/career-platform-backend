"""add fit_band_config table

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-04-10

Creates fit_band_config and seeds it with the current hardcoded thresholds
from app/services/explanations.py:fit_band_from_score.
"""
from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fit_band_config",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("band_key", sa.String(50), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("min_score", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("band_key", name="uq_fit_band_config_band_key"),
    )
    op.create_index("ix_fit_band_config_id", "fit_band_config", ["id"], unique=False)
    op.create_index("ix_fit_band_config_sort_order", "fit_band_config", ["sort_order"], unique=False)

    # Seed with current hardcoded thresholds
    op.execute("""
        INSERT INTO fit_band_config (band_key, label, min_score, sort_order)
        VALUES
          ('high_potential', 'High Potential', 80, 1),
          ('strong',         'Strong',         65, 2),
          ('promising',      'Promising',       50, 3),
          ('developing',     'Developing',      35, 4),
          ('exploring',      'Exploring',        0, 5)
    """)


def downgrade() -> None:
    op.drop_index("ix_fit_band_config_sort_order", table_name="fit_band_config")
    op.drop_index("ix_fit_band_config_id", table_name="fit_band_config")
    op.drop_table("fit_band_config")
