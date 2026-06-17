"""Add weight approval spine — Stage 1 (schema only)

Revision ID: f2a3b4c5d6e7
Revises: c9e1a2f3b456
Create Date: 2026-06-17 00:00:00.000000

WHAT THIS MIGRATION DOES
------------------------
Stage 1 of the weight-change approval workflow.  Pure schema work; no
existing tables, endpoints, or services are modified.

Changes:
  1. Creates weight_change_requests — envelope for draft → review → promote
     workflow over career ↔ key-skill weight edits.

  2. Adds careers.weight_change_policy (String, NOT NULL, default 'gated').
     All existing rows are backfilled to 'gated' automatically via the
     server-side default (PostgreSQL 11+ applies DEFAULT on existing rows
     when the column is added with NOT NULL DEFAULT — no separate UPDATE
     required).

INERT BY DESIGN
---------------
Applying this migration has zero effect on any existing query or endpoint.
weight_change_requests is empty.  careers.weight_change_policy has a
default but nothing reads it yet — it is a governance hook for later stages.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'c9e1a2f3b456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. weight_change_requests table ──────────────────────────────────────
    op.create_table(
        'weight_change_requests',
        sa.Column('id',     sa.Integer(), nullable=False),
        sa.Column('title',  sa.String(200), nullable=True),

        # status: draft | pending_review | approved | rejected | promoted
        # Transitions enforced in service layer — see WeightChangeRequest docstring.
        sa.Column('status', sa.String(20),  nullable=False, server_default='draft'),
        sa.Column('scope',  sa.String(10),  nullable=False, server_default='single'),

        # Full before/after snapshot per career — JSONB in PostgreSQL
        sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),

        # Authorship
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at',
                  sa.DateTime(timezone=True),
                  server_default=sa.func.now(),
                  nullable=False),

        # Review
        sa.Column('submitted_at',     sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by',      sa.Integer(),               nullable=True),
        sa.Column('reviewed_at',      sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_level',     sa.Integer(),  nullable=False, server_default='1'),
        sa.Column('decision_comment', sa.Text(),     nullable=True),

        # Promotion
        sa.Column('promoted_at',
                  sa.DateTime(timezone=True), nullable=True),
        sa.Column('vectors_recomputed',
                  sa.Boolean(), nullable=False, server_default=sa.false()),

        # Constraints
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Indices: status (reviewers filter by it) and created_by (author's own list)
    op.create_index(
        op.f('ix_weight_change_requests_id'),
        'weight_change_requests', ['id'], unique=False,
    )
    op.create_index(
        op.f('ix_weight_change_requests_status'),
        'weight_change_requests', ['status'], unique=False,
    )
    op.create_index(
        op.f('ix_weight_change_requests_created_by'),
        'weight_change_requests', ['created_by'], unique=False,
    )

    # ── 2. careers.weight_change_policy ──────────────────────────────────────
    # PostgreSQL 11+: ADD COLUMN … NOT NULL DEFAULT '...' is a metadata-only
    # operation — no table rewrite, existing rows immediately return 'gated'.
    op.add_column(
        'careers',
        sa.Column(
            'weight_change_policy',
            sa.String(10),
            nullable=False,
            server_default='gated',
        ),
    )


def downgrade() -> None:
    # Remove in reverse order

    # ── 2. Drop careers.weight_change_policy ─────────────────────────────────
    op.drop_column('careers', 'weight_change_policy')

    # ── 1. Drop weight_change_requests ───────────────────────────────────────
    op.drop_index(
        op.f('ix_weight_change_requests_created_by'),
        table_name='weight_change_requests',
    )
    op.drop_index(
        op.f('ix_weight_change_requests_status'),
        table_name='weight_change_requests',
    )
    op.drop_index(
        op.f('ix_weight_change_requests_id'),
        table_name='weight_change_requests',
    )
    op.drop_table('weight_change_requests')
