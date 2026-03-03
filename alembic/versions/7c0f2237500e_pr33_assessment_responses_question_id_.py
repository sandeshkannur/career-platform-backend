"""PR33 assessment_responses question_id int FK + question_code

Revision ID: 7c0f2237500e
Revises: 8baaf45df8af
Create Date: 2026-02-04 16:18:14.254999

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c0f2237500e'
down_revision: Union[str, None] = '8baaf45df8af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Rename existing string question_id -> question_code
    op.alter_column(
        "assessment_responses",
        "question_id",
        new_column_name="question_code",
        existing_type=sa.VARCHAR(),
        existing_nullable=False,
    )

    # 2) Add new INT question_id (nullable for backfill phase)
    op.add_column("assessment_responses", sa.Column("question_id", sa.Integer(), nullable=True))

    # 3) Backfill INT question_id from old values (now in question_code)
    op.execute(
        """
        UPDATE assessment_responses
        SET question_id = (question_code::int)
        WHERE question_code ~ '^[0-9]+$';
        """
    )

    # 4) Hard guard: stop if any rows couldn't be backfilled
    op.execute(
        """
        DO $$
        DECLARE bad_count integer;
        BEGIN
          SELECT COUNT(*) INTO bad_count
          FROM assessment_responses
          WHERE question_id IS NULL;

          IF bad_count > 0 THEN
            RAISE EXCEPTION 'PR33 migration blocked: % assessment_responses rows have NULL question_id after backfill', bad_count;
          END IF;
        END $$;
        """
    )

    # 5) Enforce NOT NULL
    op.alter_column("assessment_responses", "question_id", nullable=False)

    # 6) Replace uniqueness: drop old unique (assessment_id, question_id[varchar->now question_code])
    #    and create new unique (assessment_id, question_id[int])
    op.drop_constraint(
        "uq_assessment_responses_assessment_question",
        "assessment_responses",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_assessment_responses_assessment_question",
        "assessment_responses",
        ["assessment_id", "question_id"],
    )

    # 7) Add FK: assessment_responses.question_id -> questions.id
    op.create_foreign_key(
        "assessment_responses_question_id_fkey",
        "assessment_responses",
        "questions",
        ["question_id"],
        ["id"],
    )

    # 8) Helpful index for joins
    op.create_index(
        "ix_assessment_responses_question_id",
        "assessment_responses",
        ["question_id"],
    )

    # 9) Stabilize question_code as external identifier where possible:
    #    if questions.question_code exists, prefer it.
    op.execute(
        """
        UPDATE assessment_responses ar
        SET question_code = COALESCE(q.question_code, ar.question_code)
        FROM questions q
        WHERE q.id = ar.question_id;
        """
    )


def downgrade() -> None:
    # Reverse of upgrade()

    op.drop_index("ix_assessment_responses_question_id", table_name="assessment_responses")

    op.drop_constraint(
        "assessment_responses_question_id_fkey",
        "assessment_responses",
        type_="foreignkey",
    )

    op.drop_constraint(
        "uq_assessment_responses_assessment_question",
        "assessment_responses",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_assessment_responses_assessment_question",
        "assessment_responses",
        ["assessment_id", "question_code"],
    )

    op.drop_column("assessment_responses", "question_id")

    op.alter_column(
        "assessment_responses",
        "question_code",
        new_column_name="question_id",
        existing_type=sa.VARCHAR(),
        existing_nullable=False,
    )
