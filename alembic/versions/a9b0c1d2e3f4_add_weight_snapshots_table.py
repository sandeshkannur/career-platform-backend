"""Add weight_snapshots table (restore-point Stage 1)

Revision ID: a9b0c1d2e3f4
Revises: f2a3b4c5d6e7
Create Date: 2026-06-18 00:00:00.000000

WHAT THIS MIGRATION DOES
------------------------
Stage 1 of the weight-snapshot / restore-point system.
Pure schema work; no existing tables, endpoints, or services are modified.

Changes:
  1. Creates weight_snapshots — named checkpoints of career_keyskill_association
     state, captured either manually or automatically on promote.

INERT BY DESIGN
---------------
Applying this migration has zero effect on any existing query or endpoint.
weight_snapshots is empty. Nothing reads or writes it yet (endpoints come in
Stage 1 app code, restore in Stage 3).

Schema notes:
  - snapshot JSONB: [{career_id, keyskill_id, weight_percentage}, ...]
    Flat/denormalised form so a full restore is a single JSONB read with no
    joins.
  - scope_type: 'full' (whole table) or 'career' (single career, scope_ref=career_id)
  - source: 'manual' | 'auto_promote' | 'pre_restore'
    'pre_restore' is reserved for Stage 3 and never written in Stage 1.
  - wcr_id: nullable FK back to weight_change_requests — set for auto_promote
    captures, NULL for manual ones.
  - name UNIQUE: system-generated, collision-safe timestamp slug.
  - alias: human-friendly label, nullable, no uniqueness requirement.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a9b0c1d2e3f4'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'weight_snapshots',

        sa.Column('id', sa.Integer(), nullable=False),

        # System-generated unique slug (e.g. snap-20260618-143022-auto_promote-full)
        sa.Column('name', sa.String(100), nullable=False),

        # Human-friendly label — optional, not unique
        sa.Column('alias', sa.String(200), nullable=True),

        sa.Column('reason', sa.Text(), nullable=True),

        # 'full' | 'career'
        sa.Column('scope_type', sa.String(20), nullable=False),

        # career_id when scope_type='career', NULL when scope_type='full'
        sa.Column('scope_ref', sa.Integer(), nullable=True),

        # [{career_id, keyskill_id, weight_percentage}, ...]
        sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),

        # 'manual' | 'auto_promote' | 'pre_restore'
        sa.Column('source', sa.String(20), nullable=False),

        # NULL for manual captures; set for auto_promote
        sa.Column('wcr_id', sa.Integer(), nullable=True),

        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),

        # Constraints
        sa.UniqueConstraint('name', name='uq_weight_snapshots_name'),
        sa.ForeignKeyConstraint(['scope_ref'], ['careers.id']),
        sa.ForeignKeyConstraint(['wcr_id'],    ['weight_change_requests.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index(
        op.f('ix_weight_snapshots_id'),
        'weight_snapshots', ['id'], unique=False,
    )
    op.create_index(
        op.f('ix_weight_snapshots_name'),
        'weight_snapshots', ['name'], unique=True,
    )
    op.create_index(
        op.f('ix_weight_snapshots_scope_type'),
        'weight_snapshots', ['scope_type'], unique=False,
    )
    op.create_index(
        op.f('ix_weight_snapshots_scope_ref'),
        'weight_snapshots', ['scope_ref'], unique=False,
    )
    op.create_index(
        op.f('ix_weight_snapshots_source'),
        'weight_snapshots', ['source'], unique=False,
    )
    op.create_index(
        op.f('ix_weight_snapshots_created_at'),
        'weight_snapshots', ['created_at'], unique=False,
    )
    op.create_index(
        op.f('ix_weight_snapshots_wcr_id'),
        'weight_snapshots', ['wcr_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_weight_snapshots_wcr_id'),     table_name='weight_snapshots')
    op.drop_index(op.f('ix_weight_snapshots_created_at'), table_name='weight_snapshots')
    op.drop_index(op.f('ix_weight_snapshots_source'),     table_name='weight_snapshots')
    op.drop_index(op.f('ix_weight_snapshots_scope_ref'),  table_name='weight_snapshots')
    op.drop_index(op.f('ix_weight_snapshots_scope_type'), table_name='weight_snapshots')
    op.drop_index(op.f('ix_weight_snapshots_name'),       table_name='weight_snapshots')
    op.drop_index(op.f('ix_weight_snapshots_id'),         table_name='weight_snapshots')
    op.drop_table('weight_snapshots')
