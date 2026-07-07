"""Add cluster_translations table + seed Kannada cluster names

Follows the PR21 i18n convention (question_translations / facet_translations):
one dedicated table per translated entity, locale FK -> languages.code.

Seeding matches career_clusters by NAME, not by hardcoded id — the live
cluster ids (31–45) differ from the ids in the original locale spreadsheet
(data/Locale/CCluster_kn_details.xlsx, ids 1–16). Long-form names from that
spreadsheet are included as match aliases so the seed also works on
environments that still carry the long cluster names.

Revision ID: d4f8a1b6c2e7
Revises: f6a1b2c3d4e5
Create Date: 2026-07-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4f8a1b6c2e7'
down_revision: Union[str, None] = 'f6a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# english career_clusters.name (short live name and/or long legacy alias) -> Kannada name
#
# Values are copied VERBATIM from the shipped frontend locale strings
# (index bundle, home.clusters.* keys) so the PDF matches what students already
# see on screen — including the "&" separator convention.
#
# NOTE (deliberate, 2026-07-07): "ಅತಿಥ್ಯ" (Hospitality) matches the frontend's
# existing spelling even though the standard Kannada spelling is "ಆತಿಥ್ಯ".
# Consistency with the live UI was chosen over correctness here; reconcile the
# spelling platform-wide (frontend + this seed) in a future content pass.
_KN_CLUSTER_NAMES = {
    # live short names (career_clusters.name in production)
    "Agriculture": "ಕೃಷಿ & ನೈಸರ್ಗಿಕ ಸಂಪನ್ಮೂಲಗಳು",
    "Architecture": "ವಾಸ್ತುಶಿಲ್ಪ & ನಿರ್ಮಾಣ",
    "Arts & A/V": "ಕಲೆ & ಸಂವಹನ",
    "Business": "ವ್ಯವಹಾರ & ಆಡಳಿತ",
    "Education": "ಶಿಕ್ಷಣ & ತರಬೇತಿ",
    "Finance": "ಹಣಕಾಸು",
    "Government": "ಸರ್ಕಾರ & ಸಾರ್ವಜನಿಕ ಆಡಳಿತ",
    "Health Sci": "ಆರೋಗ್ಯ ವಿಜ್ಞಾನ",
    "Hospitality": "ಅತಿಥ್ಯ & ಪ್ರವಾಸೋದ್ಯಮ",
    "Human Serv": "ಮಾನವ ಸೇವೆಗಳು",
    "Info Tech": "ಮಾಹಿತಿ ತಂತ್ರಜ್ಞಾನ",
    "Law/Safety": "ಕಾನೂನು & ಸಾರ್ವಜನಿಕ ಸುರಕ್ಷತೆ",
    "Manufacturing": "ಉತ್ಪಾದನೆ",
    "Marketing": "ಮಾರ್ಕೆಟಿಂಗ್ & ಮಾರಾಟ",
    "STEM": "STEM",
    # long-form aliases (CCluster_kn_details.xlsx / classic CTE cluster names) —
    # same frontend values, keyed by the legacy long English names
    "Agriculture, Food & Natural Resources": "ಕೃಷಿ & ನೈಸರ್ಗಿಕ ಸಂಪನ್ಮೂಲಗಳು",
    "Architecture & Construction": "ವಾಸ್ತುಶಿಲ್ಪ & ನಿರ್ಮಾಣ",
    "Arts, A/V Technology & Communications": "ಕಲೆ & ಸಂವಹನ",
    "Business, Management & Administration": "ವ್ಯವಹಾರ & ಆಡಳಿತ",
    "Education & Training": "ಶಿಕ್ಷಣ & ತರಬೇತಿ",
    "Government & Public Administration": "ಸರ್ಕಾರ & ಸಾರ್ವಜನಿಕ ಆಡಳಿತ",
    "Health Science": "ಆರೋಗ್ಯ ವಿಜ್ಞಾನ",
    "Hospitality & Tourism": "ಅತಿಥ್ಯ & ಪ್ರವಾಸೋದ್ಯಮ",
    "Human Services": "ಮಾನವ ಸೇವೆಗಳು",
    "Information Technology": "ಮಾಹಿತಿ ತಂತ್ರಜ್ಞಾನ",
    "Law, Public Safety, Corrections & Security": "ಕಾನೂನು & ಸಾರ್ವಜನಿಕ ಸುರಕ್ಷತೆ",
    "Marketing, Sales & Service": "ಮಾರ್ಕೆಟಿಂಗ್ & ಮಾರಾಟ",
    "Science, Technology, Engineering & Mathematics (STEM)": "STEM",
    "Transportation, Distribution & Logistics": "ಸಾರಿಗೆ & ಲಾಜಿಸ್ಟಿಕ್ಸ್",
}


def upgrade() -> None:
    op.create_table(
        "cluster_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cluster_id", sa.Integer(), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["cluster_id"], ["career_clusters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["locale"], ["languages.code"], ondelete="RESTRICT"),
        sa.UniqueConstraint("cluster_id", "locale", name="uq_ct_cluster_locale"),
    )
    op.create_index("ix_ct_locale", "cluster_translations", ["locale"])
    op.create_index("ix_ct_cluster_id", "cluster_translations", ["cluster_id"])

    # Seed Kannada names by matching on career_clusters.name (idempotent).
    conn = op.get_bind()
    for en_name, kn_name in _KN_CLUSTER_NAMES.items():
        conn.execute(
            sa.text(
                """
                INSERT INTO cluster_translations (cluster_id, locale, name)
                SELECT id, 'kn', :kn_name FROM career_clusters WHERE name = :en_name
                ON CONFLICT (cluster_id, locale) DO NOTHING
                """
            ),
            {"kn_name": kn_name, "en_name": en_name},
        )


def downgrade() -> None:
    op.drop_index("ix_ct_cluster_id", table_name="cluster_translations")
    op.drop_index("ix_ct_locale", table_name="cluster_translations")
    op.drop_table("cluster_translations")
