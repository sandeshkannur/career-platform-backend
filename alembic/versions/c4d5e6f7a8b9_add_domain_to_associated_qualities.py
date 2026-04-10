"""add domain to associated_qualities

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-04-10

Adds a nullable domain column to associated_qualities and populates it
based on chapter groupings:
  Chapters 1–2 (AQ_01–AQ_10) → Cognitive
  Chapters 3–4 (AQ_11–AQ_20) → Behavioral
  Chapter 5    (AQ_21–AQ_25) → Emotional
"""
from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add the column
    op.add_column(
        "associated_qualities",
        sa.Column("domain", sa.String(length=50), nullable=True),
    )

    # 2) Populate — chapters 1–2: Cognitive
    op.execute(
        "UPDATE associated_qualities"
        " SET domain = 'Cognitive'"
        " WHERE aq_id IN ('AQ_01','AQ_02','AQ_03','AQ_04','AQ_05',"
        "                  'AQ_06','AQ_07','AQ_08','AQ_09','AQ_10')"
    )

    # 3) Populate — chapters 3–4: Behavioral
    op.execute(
        "UPDATE associated_qualities"
        " SET domain = 'Behavioral'"
        " WHERE aq_id IN ('AQ_11','AQ_12','AQ_13','AQ_14','AQ_15',"
        "                  'AQ_16','AQ_17','AQ_18','AQ_19','AQ_20')"
    )

    # 4) Populate — chapter 5: Emotional
    op.execute(
        "UPDATE associated_qualities"
        " SET domain = 'Emotional'"
        " WHERE aq_id IN ('AQ_21','AQ_22','AQ_23','AQ_24','AQ_25')"
    )


def downgrade() -> None:
    op.drop_column("associated_qualities", "domain")
