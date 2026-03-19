# PR-09 Local DB Drift Findings

## Alembic State
Local alembic current:
- 3293623a055c

## Observed DB Reality
The following tables already exist physically in local DB:
- consent_logs
- assessment_questions
- question_student_skill_weights
- skill_keyskill_map

This means the local DB is ahead of recorded Alembic history for some objects.

## PR-09 Table Validation

### question_student_skill_weights
Observed:
- table exists
- expected columns exist
- PK exists
- FK to questions(id) with ON DELETE CASCADE exists
- FK to skills(id) exists
- unique(question_id, skill_id) exists
- expected indexes exist

Assessment:
- structurally aligned with PR-09 migration

### skill_keyskill_map
Observed:
- table exists
- expected columns exist
- PK exists
- FK to skills(id) exists
- FK to keyskills(id) exists
- unique(skill_id, keyskill_id) exists
- extra unique index exists: ux_skill_keyskill
- separate non-unique indexes on skill_id/keyskill_id not observed
- weight default not shown in table description

Assessment:
- broadly aligned but not identical to PR-09 migration

### assessment_questions
Observed:
- table exists
- expected columns exist
- PK exists
- FK to assessments(id) exists
- FK to questions(id) exists
- expected indexes exist
- extra unique index exists: ux_assessment_questions_version_question

Assessment:
- parent migration object already present in local DB

## Decision
This DB should not be used to apply PR-09 migration directly because objects already exist and Alembic history is drifted.

## Safe Next Direction
Use this local DB only for structural comparison and evidence capture.
If migration execution must be validated, use a clean validation database or a freshly recreated local DB.
