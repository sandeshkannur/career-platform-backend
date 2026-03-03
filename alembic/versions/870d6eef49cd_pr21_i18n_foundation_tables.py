"""PR21 i18n foundation tables

Revision ID: 870d6eef49cd
Revises: c1fb35b70dc4
Create Date: 2026-02-15 22:49:55.580097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '870d6eef49cd'
down_revision: Union[str, None] = 'c1fb35b70dc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- PR21: i18n foundation (additive; do not break existing column-based i18n) ---

    # 1) languages: canonical list of supported locales
    op.create_table(
        "languages",
        sa.Column("code", sa.String(length=20), primary_key=True),  # e.g., en, hi, ta, kn
        sa.Column("name", sa.String(length=80), nullable=False),     # e.g., English
        sa.Column("native_name", sa.String(length=80), nullable=True),  # e.g., ಕನ್ನಡ
        sa.Column("direction", sa.String(length=3), nullable=False, server_default="ltr"),  # ltr/rtl
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Optional: direction guardrail (simple, deterministic)
    op.create_check_constraint(
        "ck_languages_direction_ltr_rtl",
        "languages",
        "direction IN ('ltr', 'rtl')",
    )

    # Seed minimal languages for beta (additive; safe if table is new)
    op.bulk_insert(
        sa.table(
            "languages",
            sa.column("code", sa.String),
            sa.column("name", sa.String),
            sa.column("native_name", sa.String),
            sa.column("direction", sa.String),
            sa.column("is_active", sa.Boolean),
        ),
        [
            {"code": "en", "name": "English", "native_name": "English", "direction": "ltr", "is_active": True},
            {"code": "hi", "name": "Hindi", "native_name": "हिन्दी", "direction": "ltr", "is_active": True},
            {"code": "ta", "name": "Tamil", "native_name": "தமிழ்", "direction": "ltr", "is_active": True},
            {"code": "kn", "name": "Kannada", "native_name": "ಕನ್ನಡ", "direction": "ltr", "is_active": True},
        ],
    )

    # 2) question_translations: scalable translations for questions (unlimited locales)
    op.create_table(
        "question_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assessment_version", sa.String(length=50), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["locale"], ["languages.code"], ondelete="RESTRICT"),
        sa.UniqueConstraint("assessment_version", "question_id", "locale", name="uq_qt_assessment_qid_locale"),
    )
    op.create_index("ix_qt_locale", "question_translations", ["locale"])
    op.create_index("ix_qt_assessment_version", "question_translations", ["assessment_version"])
    op.create_index("ix_qt_question_id", "question_translations", ["question_id"])

    # 3) explanation_translations: additive compatibility translation table
    # NOTE: explainability_content remains source-of-truth today; this table enables future scale + unified resolver.
    op.create_table(
        "explanation_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_version", sa.String(length=32), nullable=False),  # maps to explainability_content.version
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("explanation_key", sa.String(length=120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["locale"], ["languages.code"], ondelete="RESTRICT"),
        sa.UniqueConstraint("content_version", "locale", "explanation_key", name="uq_et_v_l_k"),
    )
    op.create_index("ix_et_locale", "explanation_translations", ["locale"])
    op.create_index("ix_et_content_version", "explanation_translations", ["content_version"])
    op.create_index("ix_et_explanation_key", "explanation_translations", ["explanation_key"])

    # 4) facet_translations will be added in PR21 AFTER verifying your facet table name.
    # We intentionally do not create it in this migration to avoid choosing an incorrect FK target.


def downgrade() -> None:
    # Reverse order (FK dependencies)
    op.drop_index("ix_et_explanation_key", table_name="explanation_translations")
    op.drop_index("ix_et_content_version", table_name="explanation_translations")
    op.drop_index("ix_et_locale", table_name="explanation_translations")
    op.drop_table("explanation_translations")

    op.drop_index("ix_qt_question_id", table_name="question_translations")
    op.drop_index("ix_qt_assessment_version", table_name="question_translations")
    op.drop_index("ix_qt_locale", table_name="question_translations")
    op.drop_table("question_translations")

    op.drop_constraint("ck_languages_direction_ltr_rtl", "languages", type_="check")
    op.drop_table("languages")