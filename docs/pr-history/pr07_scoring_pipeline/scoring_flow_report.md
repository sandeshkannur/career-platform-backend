# scoring_flow_report.md

## 1. Objective
Document the current implemented scoring pipeline for PR-07 without changing business behavior, schema, or API contracts.

## 2. Validation Outcome
PR-07 is confirmed as a validation/documentation item.
No backend change is justified at this stage.

## 3. Confirmed Scoring Entrypoint
Primary runtime entrypoint:
- POST /{assessment_id}/submit-assessment

Confirmed sequence inside submit_assessment:
1. Validate assessment ownership
2. Enforce response membership and answer scale checks
3. Call compute_and_persist_skill_scores(...)
4. Handle idempotency fallback if scores already exist
5. Sync persisted skill scores to keyskills
6. Recompute analytics snapshot
7. Build tier output
8. Compute careers for assessment result payload
9. Upsert AssessmentResult

## 4. Implemented Scoring Flow (Actual)
Implemented backend flow is:

AssessmentResponse
-> question_student_skill_weights
-> compute_and_persist_skill_scores()
-> student_skill_scores
-> sync_skill_scores_to_keyskills()
-> student_keyskill_map
-> get_student_keyskill_scores()
-> compute_career_scores()
-> compute_cluster_scores()
-> recommendations / scorecard / paid analytics / assessment result generation

## 5. Skill Scoring Logic
Service:
- app/services/assessment_scoring_service.py

Confirmed behavior:
- Reads persisted assessment responses
- Prefers answer_value; falls back to parsing answer
- Validates numeric range
- Loads question_student_skill_weights (QSSW)
- Raises explicit error if QSSW missing for any question
- Normalizes weights per question
- Computes contribution = answer_value * normalized_weight
- Aggregates by skill
- Persists one row per:
  (assessment_id, scoring_config_version, skill_id)

Stored fields include:
- raw_total
- question_count
- avg_raw
- scaled_0_100

Additional notes:
- Existing stale rows for removed skills are cleaned up before persistence
- Writes are idempotent via unique constraint
- Internal contribution trace seed is also produced

## 6. student_skill_scores Role
Table:
- student_skill_scores

Purpose:
- Canonical persisted scoring output for per-skill assessment results

Confirmed model behavior:
- Unique key:
  (assessment_id, scoring_config_version, skill_id)
- Stores:
  raw_total, question_count, avg_raw, scaled_0_100
- Also has additive nullable HSI fields:
  hsi_score, cps_score_used, assessment_version

Important implementation note:
- student_id in this table currently points to users.id, not students.id

## 7. Skill -> KeySkill Sync Logic
Service:
- app/services/keyskill_sync_service.py

Confirmed behavior:
- Reads student_skill_scores for assessment_id + scoring_config_version
- Maps B7 student_id/users.id -> students.id using students.user_id
- Loads skill_keyskill_map for contributing skills
- Aggregates scaled_0_100 into keyskill weighted averages
- Upserts into student_keyskill_map by:
  (student_id, keyskill_id)

Confirmed output:
- student_keyskill_map.score is the persisted keyskill strength score (0..100)

## 8. Career and Cluster Scoring Logic
Service:
- app/services/scoring.py

Confirmed behavior:
- Reads student_keyskill_map
- Normalizes keyskill score to 0..1
- Computes career score as:
  sum(student_keyskill_score * weight_percentage)
- Uses career_keyskill_weights_effective_int_v if available
- Falls back to career_keyskill_association if the view is unavailable
- Computes cluster score as:
  max(career scores inside that cluster)

## 9. Tiering and Assessment Result Behavior
Within submit_assessment:
- Tiering is based on scaled_0_100
- HSI values are persisted separately
- Current beta policy keeps tiers based on scaled_0_100, not HSI
- AssessmentResult is upserted with:
  - skill_tiers
  - recommended_careers
  - version pins
  - contribution trace

## 10. Key Production-Safe Findings
1. The scoring path already exists and is implemented end-to-end.
2. student_skill_scores is the core persisted scoring table for PR-07 scope.
3. keyskills are not computed directly inside the primary scoring engine; they are derived in a post-scoring sync step.
4. Career and cluster scoring are downstream consumers of student_keyskill_map.
5. Idempotency is already intentionally built into the scoring path.

## 11. Gap Assessment
No scoring redesign is justified from PR-07 evidence.

Potential observations to note only, not change in PR-07:
- student_skill_scores.student_id stores users.id, while downstream keyskill logic needs students.id and performs mapping.
- student_keyskill_map does not carry assessment/version fields, so latest upsert wins by student+keyskill.
- Legacy/mixed normalization handling exists in downstream scoring.

These are observations only for future controlled review, not action items in PR-07.

## 12. API / Frontend Contract Impact
None.
PR-07 requires no API change and no response shape change.

## 13. Conclusion
The current implemented scoring pipeline is confirmed as:

Question Response
-> Question-to-Skill weighted scoring
-> student_skill_scores persistence
-> Skill-to-KeySkill weighted sync
-> student_keyskill_map persistence
-> Career scoring
-> Cluster scoring
-> Tiered/student-safe result generation

PR-07 conclusion:
- Validation complete
- No schema change required
- No API change required
- No backend logic change required at this stage

## 14. Evidence Files Used
Validation for this PR was based on direct inspection of:

- pr07_scoring_pipeline\assessment_scoring_service_core.txt
- pr07_scoring_pipeline\keyskill_sync_core.txt
- pr07_scoring_pipeline\scoring_service_core.txt
- pr07_scoring_pipeline\submit_assessment_core.txt
- pr07_scoring_pipeline\student_skill_score_model.txt

## 15. PR-07 Final Status
Status: Completed
Type: Validation only
Production impact: None
Schema impact: None
API impact: None
Frontend impact: None
Recommended next step: Proceed to next backlog item only if it is based on a proven gap, not assumed redesign.
