# PR-06 Assessment Flow Validation

## PR Details

- **PR ID:** PR-06
- **PR Name:** Assessment Flow Validation
- **Type:** Validation
- **Priority Tier:** P0
- **Beta Critical:** Yes
- **Scope / Concern:** Validate question count and randomisation behavior
- **DB Objects Reviewed:** questions, ssessments, ssessment_questions, ssessment_responses
- **API Changes:** None
- **Schema Changes:** None

---

## 1. Objective

Validate whether the current backend already supports the approved product behavior for:

- assessment question count
- question randomisation
- resume-safe assessment delivery
- production-safe, frontend-compatible assessment flow

This PR is validation only.

It does **not** redesign the assessment flow and does **not** introduce schema or API changes.

---

## 2. Validation Summary

### Final Outcome

**PASS — no backend change required for PR-06**

The current backend already supports the intended assessment flow through:

1. **Randomized question selection at assessment creation time**
2. **Persistence of the selected assessment-bound question set**
3. **Deterministic question delivery after creation for resume safety**

This means the platform does **not** randomize questions on every fetch.
It randomizes once during assessment creation, then serves the persisted canonical set thereafter.

---

## 3. Files / Areas Reviewed

Primary file reviewed:

- pp/routers/assessments.py

Related behavior cross-checked from backend extract:

- pp/routers/questions_random.py

---

## 4. What Already Exists

### 4.1 Assessment creation uses pinned versions

Assessment creation logic uses pinned versions:

- ssessment_version = "v1"
- scoring_config_version = "v1"
- question_pool_version = "v1"

This confirms the backend already has a version-aware assessment shell model.

### 4.2 Assessment creation generates the canonical question set

During assessment creation:

- the question sampler _sample_75_questions_v1(...) is used
- expected output is exactly **75 questions**
- sampling is AQ-balanced
- sampled questions are persisted into ssessment_questions
- persistence is treated as the canonical question set for the assessment

### 4.3 Resume-safe runner behavior already exists

The active assessment flow uses:

- ssessment_questions as the persisted question-order source
- ssessment_responses to calculate progress
- deterministic derivation of:
  - nswered_count
  - last_answered_question_id
  - 
ext_question_id
  - is_complete

This confirms the runner is **deterministic after creation**, which is the correct design for resume-safe UX.

### 4.4 Assessment question fetch uses canonical persisted set

GET /v1/assessments/{assessment_id}/questions:

- reads the assessment
- reads ssessment_questions
- batch-loads related questions
- returns the assessment-bound set
- uses deterministic ordering based on persisted assessment question rows

This confirms question delivery is not ad hoc and not re-randomized on each fetch.

### 4.5 Separate helper endpoint exists for raw random fetch

There is also a separate endpoint:

- GET /v1/questions/random

That endpoint:

- accepts ssessment_version
- accepts request-driven count
- validates availability
- uses ORDER BY RANDOM()
- returns a random subset limited by the request count

This endpoint is **not** the same as the main student assessment runner flow.

---

## 5. Question Count Validation

## Expected Product Concern

Validate whether the backend supports product-defined question count behavior.

## Finding

The main assessment flow currently expects **75 questions** at assessment creation time.

### Evidence from code behavior

- assessment creation calls a 75-question sampler
- expected result is exactly 75 questions
- those questions are persisted into ssessment_questions
- active assessment logic later derives 	otal_questions from the persisted question set

## Conclusion

**PASS**

Question count for the main assessment runner flow is already enforced through the persisted assessment-bound question set.

### Important clarification

The separate /v1/questions/random endpoint is request-count-driven and capped independently.
That helper path should not be confused with the canonical assessment runner flow.

---

## 6. Randomisation Validation

## Expected Product Concern

Validate whether question randomisation is supported by the backend.

## Finding

Randomisation exists, but it occurs at **assessment creation time**, not on every subsequent question fetch.

### Main runner flow

- randomized sampling happens once during assessment creation
- selected questions are persisted in ssessment_questions
- later fetches are deterministic

### Helper random endpoint

- /v1/questions/random performs direct random fetch from questions
- this is a separate utility/helper behavior

## Conclusion

**PASS**

Randomisation is implemented in the backend in a production-safe way:
- randomized at creation
- deterministic during delivery

This is consistent with stable resume behavior and should be preserved.

---

## 7. Resume / Deterministic Delivery Validation

## Finding

The active assessment flow is explicitly resume-safe.

It uses:

- persisted question IDs from ssessment_questions
- persisted responses from ssessment_responses
- deterministic next-question logic
- fallback behavior only for legacy/pre-persist cases

This confirms the backend supports a stable student journey across partial completion and resume scenarios.

## Conclusion

**PASS**

Resume-safe deterministic sequencing is already implemented.

---

## 8. API / Frontend Contract Impact Check

## Result

**No API or frontend contract changes required**

The current flow already preserves:

- assessment-bound question delivery
- deterministic ordering after assessment creation
- existing response field naming
- existing active-assessment semantics
- existing student-safe question payload structure

No contract-breaking backend changes are justified in PR-06.

---

## 9. Gap Analysis

## Actual gap status

No backend gap was proven for this PR item.

What was validated instead:

- question count support exists
- randomisation support exists
- deterministic delivery exists
- assessment flow is already implemented in a production-safe manner

## Clarification identified

The only important clarification is conceptual:

- **main assessment flow** = randomize once, persist, then serve deterministically
- **helper random endpoint** = on-demand random pull from question pool

These should not be mixed together in future backlog interpretation.

---

## 10. Relevant Tables Reviewed

### ssessments
Used to store the assessment shell and version pins:
- ssessment_version
- scoring_config_version
- question_pool_version

### questions
Source pool for question selection.

### ssessment_questions
Canonical persisted assessment-bound question set.
This is the key table for deterministic assessment delivery.

### ssessment_responses
Used for progress tracking and next-question derivation during resume flow.

---

## 11. Migration Check

No migration required.

### Reason

This PR validated that the current schema and current logic already support the required assessment flow behavior.

---

## 12. Production Safety Conclusion

PR-06 should remain **validation only**.

### Safe conclusion

Do not:
- redesign the flow
- re-randomize on every fetch
- move canonical source away from ssessment_questions
- change response shapes
- introduce schema changes without a proven defect

The current design is production-safe and frontend-safe.

---

## 13. Final Verdict

# PR-06 = PASS

The backend already supports:

- approved assessment question count behavior for the main runner flow
- randomized question selection at creation time
- deterministic resume-safe delivery afterward

### Recommended action

Close PR-06 as:
- **Validation complete**
- **No code change required**
- **No migration required**
- **No API change required**

---

## 14. Explicitly Must Not Change

Do **not** change the following as part of PR-06:

- 75-question assessment creation behavior
- version pinning behavior
- persisted ssessment_questions as canonical source
- deterministic resume-safe sequencing
- active assessment response shape
- assessment question response shape
- frontend-linked ordering semantics
- student-facing payload field names

---

## 15. Optional Follow-up Note (Not Part of PR-06)

A separate code review item may be raised later for unrelated issues found outside PR-06 scope.
Any such issue should be tracked independently and must not be mixed into this validation PR.
