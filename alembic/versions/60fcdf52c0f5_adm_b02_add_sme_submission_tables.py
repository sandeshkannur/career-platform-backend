"""adm_b02_add_sme_submission_tables

Revision ID: 60fcdf52c0f5
Revises: 9839a6c4d069
Create Date: 2026-04-01 14:21:31.733734

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60fcdf52c0f5'
down_revision: Union[str, None] = '9839a6c4d069'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    ADM-B02: Create SME submission pipeline tables.

    4 new tables:
    - sme_submission_tokens  — one token per SME+career+round, with disclaimer audit trail
    - sme_aq_ratings         — 25 AQ weight ratings per submission (0.0–1.0)
    - sme_keyskill_ratings   — pre-mapped key skill ratings per submission (0.0–1.0)
    - sme_keyskill_suggestions — SME-suggested key skills (review queue, never auto-applied)

    Rating scale: SME inputs 0–10 integer, stored as 0.0–1.0 (÷10).
    Disclaimer: v1.0 text stored in DISCLAIMER_VERSIONS constant in models.py.
    Disclaimer acceptance recorded per submission: version + timestamp + IP.
    """
    # ── sme_submission_tokens ─────────────────────────────────────────────
    op.create_table(
        "sme_submission_tokens",
        sa.Column("id",           sa.Integer(),  nullable=False),
        sa.Column("sme_id",       sa.Integer(),  nullable=False),
        sa.Column("career_id",    sa.Integer(),  nullable=False),
        sa.Column("token",        sa.String(64), nullable=False),
        sa.Column("round_number", sa.Integer(),  nullable=False, server_default="1"),
        sa.Column("status",       sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("disclaimer_version",     sa.String(10),  nullable=True),
        sa.Column("disclaimer_accepted",    sa.Boolean(),   nullable=False, server_default="false"),
        sa.Column("disclaimer_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disclaimer_ip_address",  sa.String(45),  nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["sme_id"],    ["sme_profiles.id"]),
        sa.ForeignKeyConstraint(["career_id"], ["careers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_sme_submission_tokens_token"),
        sa.UniqueConstraint("sme_id", "career_id", "round_number", name="uq_sme_token_sme_career_round"),
    )
    op.create_index("ix_sme_submission_tokens_id",     "sme_submission_tokens", ["id"],        unique=False)
    op.create_index("ix_sme_submission_tokens_sme_id", "sme_submission_tokens", ["sme_id"],    unique=False)
    op.create_index("ix_sme_submission_tokens_career",  "sme_submission_tokens", ["career_id"], unique=False)
    op.create_index("ix_sme_submission_tokens_token",   "sme_submission_tokens", ["token"],     unique=True)
    op.create_index("ix_sme_submission_tokens_status",  "sme_submission_tokens", ["status"],    unique=False)

    # ── sme_aq_ratings ────────────────────────────────────────────────────
    op.create_table(
        "sme_aq_ratings",
        sa.Column("id",            sa.Integer(),     nullable=False),
        sa.Column("token_id",      sa.Integer(),     nullable=False),
        sa.Column("sme_id",        sa.Integer(),     nullable=False),
        sa.Column("career_id",     sa.Integer(),     nullable=False),
        sa.Column("aq_code",       sa.String(20),    nullable=False),
        sa.Column("weight_rating", sa.Float(),       nullable=False),
        sa.Column("confidence",    sa.Float(),       nullable=True),
        sa.Column("notes",         sa.Text(),        nullable=True),
        sa.Column("submitted_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["token_id"],  ["sme_submission_tokens.id"]),
        sa.ForeignKeyConstraint(["sme_id"],    ["sme_profiles.id"]),
        sa.ForeignKeyConstraint(["career_id"], ["careers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_id", "aq_code", name="uq_sme_aq_rating_token_aq"),
    )
    op.create_index("ix_sme_aq_ratings_id",        "sme_aq_ratings", ["id"],                   unique=False)
    op.create_index("ix_sme_aq_ratings_token_id",  "sme_aq_ratings", ["token_id"],              unique=False)
    op.create_index("ix_sme_aq_ratings_sme_id",    "sme_aq_ratings", ["sme_id"],                unique=False)
    op.create_index("ix_sme_aq_ratings_career_aq", "sme_aq_ratings", ["career_id", "aq_code"],  unique=False)

    # ── sme_keyskill_ratings ──────────────────────────────────────────────
    op.create_table(
        "sme_keyskill_ratings",
        sa.Column("id",            sa.Integer(), nullable=False),
        sa.Column("token_id",      sa.Integer(), nullable=False),
        sa.Column("sme_id",        sa.Integer(), nullable=False),
        sa.Column("career_id",     sa.Integer(), nullable=False),
        sa.Column("keyskill_id",   sa.Integer(), nullable=False),
        sa.Column("weight_rating", sa.Float(),   nullable=False),
        sa.Column("confidence",    sa.Float(),   nullable=True),
        sa.Column("notes",         sa.Text(),    nullable=True),
        sa.Column("submitted_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["token_id"],    ["sme_submission_tokens.id"]),
        sa.ForeignKeyConstraint(["sme_id"],      ["sme_profiles.id"]),
        sa.ForeignKeyConstraint(["career_id"],   ["careers.id"]),
        sa.ForeignKeyConstraint(["keyskill_id"], ["keyskills.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_id", "keyskill_id", name="uq_sme_keyskill_rating_token_ks"),
    )
    op.create_index("ix_sme_keyskill_ratings_id",         "sme_keyskill_ratings", ["id"],                        unique=False)
    op.create_index("ix_sme_keyskill_ratings_token_id",   "sme_keyskill_ratings", ["token_id"],                  unique=False)
    op.create_index("ix_sme_keyskill_ratings_sme_id",     "sme_keyskill_ratings", ["sme_id"],                    unique=False)
    op.create_index("ix_sme_keyskill_ratings_career_ks",  "sme_keyskill_ratings", ["career_id", "keyskill_id"],  unique=False)

    # ── sme_keyskill_suggestions ──────────────────────────────────────────
    op.create_table(
        "sme_keyskill_suggestions",
        sa.Column("id",                    sa.Integer(),     nullable=False),
        sa.Column("token_id",              sa.Integer(),     nullable=False),
        sa.Column("sme_id",                sa.Integer(),     nullable=False),
        sa.Column("career_id",             sa.Integer(),     nullable=False),
        sa.Column("existing_keyskill_id",  sa.Integer(),     nullable=True),
        sa.Column("suggested_name",        sa.String(200),   nullable=True),
        sa.Column("suggested_description", sa.Text(),        nullable=True),
        sa.Column("importance_rating",     sa.Float(),       nullable=True),
        sa.Column("rationale",             sa.Text(),        nullable=True),
        sa.Column("review_status",         sa.String(20),    nullable=False, server_default="pending"),
        sa.Column("reviewed_by",           sa.Integer(),     nullable=True),
        sa.Column("reviewed_at",           sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at",          sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["token_id"],             ["sme_submission_tokens.id"]),
        sa.ForeignKeyConstraint(["sme_id"],               ["sme_profiles.id"]),
        sa.ForeignKeyConstraint(["career_id"],            ["careers.id"]),
        sa.ForeignKeyConstraint(["existing_keyskill_id"], ["keyskills.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"],          ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sme_keyskill_suggestions_id",            "sme_keyskill_suggestions", ["id"],            unique=False)
    op.create_index("ix_sme_keyskill_suggestions_token_id",      "sme_keyskill_suggestions", ["token_id"],      unique=False)
    op.create_index("ix_sme_keyskill_suggestions_sme_id",        "sme_keyskill_suggestions", ["sme_id"],        unique=False)
    op.create_index("ix_sme_keyskill_suggestions_career_id",     "sme_keyskill_suggestions", ["career_id"],     unique=False)
    op.create_index("ix_sme_keyskill_suggestions_review_status", "sme_keyskill_suggestions", ["review_status"], unique=False)


def downgrade() -> None:
    """Remove ADM-B02 SME submission pipeline tables (rollback)."""
    op.drop_table("sme_keyskill_suggestions")
    op.drop_table("sme_keyskill_ratings")
    op.drop_table("sme_aq_ratings")
    op.drop_table("sme_submission_tokens")
