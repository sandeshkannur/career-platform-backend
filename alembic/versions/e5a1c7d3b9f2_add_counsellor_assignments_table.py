"""add counsellor_assignments table

Phase 1 of counsellor-student assignments: table + indexes only.
assignment_type ships with all four product values (admin_assigned,
school_auto, self_claimed, region_auto) so wiring school/region
auto-assignment later needs no follow-up migration. No uniqueness on
student_id — a student can have multiple active counsellors.

Revision ID: e5a1c7d3b9f2
Revises: b7c4e9a2d1f8
Create Date: 2026-07-09

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e5a1c7d3b9f2"
down_revision = "b7c4e9a2d1f8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "counsellor_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "counsellor_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assignment_type", sa.String(length=32), nullable=False),
        sa.Column(
            "assigned_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint(
            "assignment_type IN ('admin_assigned', 'school_auto', 'self_claimed', 'region_auto')",
            name="ck_counsellor_assignments_type",
        ),
    )
    op.create_index("ix_counsellor_assignments_id", "counsellor_assignments", ["id"])
    op.create_index("ix_counsellor_assignments_counsellor_id", "counsellor_assignments", ["counsellor_id"])
    op.create_index("ix_counsellor_assignments_student_id", "counsellor_assignments", ["student_id"])
    op.create_index("ix_counsellor_assignments_active", "counsellor_assignments", ["active"])


def downgrade():
    op.drop_table("counsellor_assignments")
