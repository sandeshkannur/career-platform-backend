"""Add archetype classification columns to careers table

Revision ID: e7a4f9c2b1d8
Revises: d83f3b8ad226
Create Date: 2026-04-14 00:00:00.000000

Adds metadata-only columns to careers:
  archetype          — structural shape of the career's skill requirements
  career_level       — entry / mid / senior / executive
  archetype_rationale — human-readable explanation of archetype assignment

These columns do NOT affect any scoring logic. They are metadata used for
admin classification, UI display, and future recommendation grouping.

The data migration (Step 2) auto-classifies existing careers based on their
career_keyskill_association weight statistics. Rules applied in order:
  1. pinnacle     — spread >= 30 AND max_weight >= 40
  2. deep_expert  — spread 20-34 AND max_weight 25-39
  3. precision    — top keyskills are precision/technical AND spread 10-19
  4. multi_domain — 7+ keyskills AND spread <= 10
  5. gateway      — spread <= 5 (remaining unclassified)
  6. t_shaped     — everything else (safe default)

career_level defaults:
  gateway               → entry
  precision, t_shaped   → mid
  deep_expert, pinnacle, multi_domain → senior
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7a4f9c2b1d8'
down_revision: Union[str, None] = 'd83f3b8ad226'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 1: Add columns ───────────────────────────────────────────────
    op.add_column('careers', sa.Column('archetype',           sa.String(30), nullable=True))
    op.add_column('careers', sa.Column('career_level',        sa.String(20), nullable=True))
    op.add_column('careers', sa.Column('archetype_rationale', sa.Text(),     nullable=True))

    op.create_index('ix_careers_archetype',    'careers', ['archetype'],    unique=False)
    op.create_index('ix_careers_career_level', 'careers', ['career_level'], unique=False)

    # ── Step 2: Seed archetype classifications ────────────────────────────
    # Each UPDATE only touches rows that still have archetype IS NULL,
    # so the order of rules acts as a priority chain.
    conn = op.get_bind()

    # Rule 1: pinnacle — very high spread + dominant keyskill
    conn.execute(sa.text("""
        WITH career_stats AS (
            SELECT
                career_id,
                COUNT(*)                                    AS num_ks,
                MAX(weight_percentage)                      AS max_w,
                MIN(weight_percentage)                      AS min_w,
                MAX(weight_percentage) - MIN(weight_percentage) AS spread
            FROM career_keyskill_association
            GROUP BY career_id
        )
        UPDATE careers
        SET archetype = 'pinnacle'
        FROM career_stats cs
        WHERE cs.career_id = careers.id
          AND cs.spread >= 30
          AND cs.max_w  >= 40
          AND careers.archetype IS NULL
    """))

    # Rule 2: deep_expert — high spread, strong top keyskill, not pinnacle
    conn.execute(sa.text("""
        WITH career_stats AS (
            SELECT
                career_id,
                MAX(weight_percentage)                      AS max_w,
                MAX(weight_percentage) - MIN(weight_percentage) AS spread
            FROM career_keyskill_association
            GROUP BY career_id
        )
        UPDATE careers
        SET archetype = 'deep_expert'
        FROM career_stats cs
        WHERE cs.career_id = careers.id
          AND cs.spread BETWEEN 20 AND 34
          AND cs.max_w  BETWEEN 25 AND 39
          AND careers.archetype IS NULL
    """))

    # Rule 3: precision — 2+ precision/technical keyskills each >= 20%, spread 10-19
    conn.execute(sa.text("""
        WITH career_stats AS (
            SELECT
                career_id,
                MAX(weight_percentage) - MIN(weight_percentage) AS spread
            FROM career_keyskill_association
            GROUP BY career_id
        ),
        precision_careers AS (
            SELECT cka.career_id
            FROM career_keyskill_association cka
            JOIN keyskills ks ON ks.id = cka.keyskill_id
            JOIN career_stats cs ON cs.career_id = cka.career_id
            WHERE ks.name IN (
                'Grit & Self-Direction', 'Productivity', 'Time Management',
                'Technical Skills', 'Practical Problem Solving'
            )
              AND cka.weight_percentage >= 20
              AND cs.spread BETWEEN 10 AND 19
            GROUP BY cka.career_id
            HAVING COUNT(*) >= 2
        )
        UPDATE careers
        SET archetype = 'precision'
        FROM precision_careers pc
        WHERE pc.career_id = careers.id
          AND careers.archetype IS NULL
    """))

    # Rule 4: multi_domain — many keyskills, very even distribution
    conn.execute(sa.text("""
        WITH career_stats AS (
            SELECT
                career_id,
                COUNT(*)                                    AS num_ks,
                MAX(weight_percentage) - MIN(weight_percentage) AS spread
            FROM career_keyskill_association
            GROUP BY career_id
        )
        UPDATE careers
        SET archetype = 'multi_domain'
        FROM career_stats cs
        WHERE cs.career_id = careers.id
          AND cs.num_ks >= 7
          AND cs.spread <= 10
          AND careers.archetype IS NULL
    """))

    # Rule 5: gateway — very flat distribution (entry-level type)
    conn.execute(sa.text("""
        WITH career_stats AS (
            SELECT
                career_id,
                MAX(weight_percentage) - MIN(weight_percentage) AS spread
            FROM career_keyskill_association
            GROUP BY career_id
        )
        UPDATE careers
        SET archetype = 'gateway'
        FROM career_stats cs
        WHERE cs.career_id = careers.id
          AND cs.spread <= 5
          AND careers.archetype IS NULL
    """))

    # Rule 6: t_shaped — safe default for everything remaining
    conn.execute(sa.text("""
        UPDATE careers
        SET archetype = 't_shaped'
        WHERE archetype IS NULL
    """))

    # ── Step 3: Default career_level from archetype ───────────────────────
    conn.execute(sa.text("""
        UPDATE careers SET career_level = 'entry'
        WHERE archetype = 'gateway'
          AND career_level IS NULL
    """))

    conn.execute(sa.text("""
        UPDATE careers SET career_level = 'mid'
        WHERE archetype IN ('precision', 't_shaped', 'emerging')
          AND career_level IS NULL
    """))

    conn.execute(sa.text("""
        UPDATE careers SET career_level = 'senior'
        WHERE archetype IN ('deep_expert', 'pinnacle', 'multi_domain')
          AND career_level IS NULL
    """))


def downgrade() -> None:
    op.drop_index('ix_careers_career_level', table_name='careers')
    op.drop_index('ix_careers_archetype',    table_name='careers')
    op.drop_column('careers', 'archetype_rationale')
    op.drop_column('careers', 'career_level')
    op.drop_column('careers', 'archetype')
