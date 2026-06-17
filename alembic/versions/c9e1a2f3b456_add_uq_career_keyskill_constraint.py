"""Add unique constraint uq_career_keyskill to career_keyskill_association

Revision ID: c9e1a2f3b456
Revises: e7a4f9c2b1d8
Create Date: 2026-06-17 00:00:00.000000

WHY THIS MIGRATION EXISTS
--------------------------
career_keyskill_association was created in f66212d1b2fa without a PRIMARY KEY
or UNIQUE CONSTRAINT (both columns were nullable=True, no PK was declared).
The SQLAlchemy model marks both columns primary_key=True, so ORM code treats
them as a composite identity, but the actual PG table has no such constraint.

This means the upsert in POST /v1/admin/upload-career-keyskill-weights:

    INSERT INTO career_keyskill_association ...
    ON CONFLICT (career_id, keyskill_id) DO UPDATE ...

fails with:
    psycopg2.errors.InvalidColumnReference:
    there is no unique or exclusion constraint matching the ON CONFLICT specification

SAFETY NOTE
-----------
Live data was confirmed to contain ZERO duplicate (career_id, keyskill_id)
pairs before this migration was written, so CREATE UNIQUE INDEX / ADD CONSTRAINT
will succeed without needing to deduplicate first. If that assumption is ever
violated on a restore/clone, the constraint creation will fail with a clear
duplicate-key error — safe-fail behaviour, no silent data loss.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c9e1a2f3b456'
down_revision: Union[str, None] = 'e7a4f9c2b1d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adding a named UNIQUE constraint so ON CONFLICT (career_id, keyskill_id)
    # has a target.  If a duplicate somehow crept in, this will raise a
    # clear constraint-violation error rather than silently proceeding.
    op.create_unique_constraint(
        'uq_career_keyskill',
        'career_keyskill_association',
        ['career_id', 'keyskill_id'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_career_keyskill',
        'career_keyskill_association',
        type_='unique',
    )
