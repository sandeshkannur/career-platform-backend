# PR-09 Validation Notes

## Objective
Add missing scoring support tables in a production-safe, additive-only manner without changing existing API contracts or scoring behaviour.

## Confirmed Gap
From prior validation:
- `question_student_skill_weights` exists in local SQLAlchemy models
- `skill_keyskill_map` exists in local SQLAlchemy models
- neither table exists in production baseline inventory

## Additional Safety Validation
Checked production table, column, constraint, and index inventories.
No equivalent alternate production tables were found for:
- question ? skill ? weight mapping
- skill ? keyskill mapping

## Migration Outcome
Generated offline SQL successfully.

Confirmed additive DDL includes:
- CREATE TABLE `question_student_skill_weights`
- CREATE TABLE `skill_keyskill_map`
- FK to `questions.id`
- FK to `skills.id`
- FK to `keyskills.id`
- unique constraint on `(question_id, skill_id)`
- unique constraint on `(skill_id, keyskill_id)`
- supporting indexes

## Contract Impact
- No API change
- No frontend response change
- No scoring logic change in this PR
- No explainability change
- No admin workflow redesign

## PR-09 Status
Schema migration is ready for controlled application and validation.
