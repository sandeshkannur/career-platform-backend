# API Dependency Map



## PR-04 Objective

Map frontend-relevant API endpoints to backend router logic, service/query paths, and underlying database objects so future backend changes do not accidentally break production APIs or frontend-linked contracts.



This PR is analysis only.

No schema changes, API changes, or business-logic changes are introduced.


---



## Endpoint: GET /v1/recommendations/{student\_id}



**Router File:** `app/routers/recommendations.py`

- \*\*Handler Function:\*\* `get\_recommendations`

- \*\*Mounted Prefix Source:\*\* `app/main.py` → `api\_v1.include\_router(recommendations.router, prefix="/recommendations", tags=\["Recommendations"])`

- \*\*Auth Dependency:\*\* `get\_current\_active\_user`

- \*\*Role Rule:\*\* students can access only their own recommendation payload

- \*\*Direct Router DB Read:\*\*

&#x20; - `students` (lookup by `students.user\_id == current\_user.id`)

- \*\*Delegated Service Path:\*\*

&#x20; - `app.services.career\_engine.compute\_careers\_for\_student`

&#x20; - which calls `app.services.scoring.compute\_career\_scores`

&#x20; - which calls `app.services.scoring.get\_student\_keyskill\_scores`

- \*\*Confirmed Reads:\*\*

&#x20; - `students`

&#x20; - `student\_keyskill\_map`

&#x20; - `keyskills`

&#x20; - `career\_keyskill\_weights\_effective\_int\_v`

&#x20; - `career\_keyskill\_association` (fallback path if weighted view is unavailable)

&#x20; - `careers`

&#x20; - `career\_clusters` (via ORM relationship `Career.cluster`)

- \*\*Writes:\*\* none visible in router/service/scoring path

- \*\*Scoring Logic Notes:\*\*

&#x20; - student keyskill scores are read from `student\_keyskill\_map.score`

&#x20; - if `score` is NULL, legacy binary behavior treats presence as full strength (`1.0`)

&#x20; - if score is between `0–1`, it is treated as normalized

&#x20; - if score is greater than `1`, it is treated as `0–100` and normalized to `0–1`

&#x20; - career score is computed as sum of `(student\_keyskill\_score \* weight\_percentage)`

&#x20; - primary weight source is `career\_keyskill\_weights\_effective\_int\_v.effective\_weight\_int`

&#x20; - fallback weight source is `career\_keyskill\_association.weight\_percentage`

- \*\*Response Behavior:\*\*

&#x20; - computes raw recommendation payload

&#x20; - student endpoint sanitizes numeric/internal fields such as:

&#x20;   - `score`

&#x20;   - `weight`

&#x20;   - `points`

&#x20;   - `raw\_score`

&#x20;   - `scaled\_score`

&#x20;   - `top\_keyskill\_weights`

&#x20; - applies `project\_student\_safe(...)`

- \*\*Key Output Fields Observed:\*\*

&#x20; - `student\_id`

&#x20; - `recommended\_careers`

&#x20; - per career:

&#x20;   - `career\_id`

&#x20;   - `career\_code`

&#x20;   - `title`

&#x20;   - `description`

&#x20;   - `cluster`

&#x20;   - `score` (removed from student-safe output)

&#x20;   - `matched\_keyskills`

&#x20;   - `explainability`

- \*\*Frontend Contract Risk Notes:\*\*

&#x20; - student-facing contract depends on post-sanitization output shape

&#x20; - any service-layer rename/removal of keys like `career\_id`, `career\_code`, `title`, `description`, `cluster`, `matched\_keyskills`, `explainability` may break consumers

&#x20; - any change to sanitization logic may expose internal numeric fields or alter frontend-visible payload

&#x20; - recommendation logic depends on weighted DB objects, not just raw mapping tables



---



## Endpoint: GET /v1/recommendations/admin/{student\_id}



- \*\*Router File:\*\* `app/routers/recommendations.py`

- \*\*Handler Function:\*\* `get\_recommendations\_admin`

- \*\*Mounted Prefix Source:\*\* `app/main.py` → `api\_v1.include\_router(recommendations.router, prefix="/recommendations", tags=\["Recommendations"])`

- \*\*Auth Dependency:\*\* `require\_roles("admin", "counsellor")`

- \*\*Role Rule:\*\* admin/counsellor only

- \*\*Direct Router DB Read:\*\* none in route body

- \*\*Delegated Service Path:\*\*

&#x20; - `app.services.career\_engine.compute\_careers\_for\_student`

&#x20; - which calls `app.services.scoring.compute\_career\_scores`

&#x20; - which calls `app.services.scoring.get\_student\_keyskill\_scores`

- \*\*Confirmed Reads:\*\*

&#x20; - `student\_keyskill\_map`

&#x20; - `keyskills`

&#x20; - `career\_keyskill\_weights\_effective\_int\_v`

&#x20; - `career\_keyskill\_association` (fallback path if weighted view is unavailable)

&#x20; - `careers`

&#x20; - `career\_clusters`

- \*\*Writes:\*\* none visible in router/service/scoring path

- \*\*Response Behavior:\*\*

&#x20; - returns raw recommendation payload

&#x20; - numeric/internal fields are retained for admin/counsellor flow

- \*\*Frontend Contract Risk Notes:\*\*

&#x20; - admin/counsellor response depends directly on service-layer raw output structure

&#x20; - weighted view dependency is important for backend safety

&#x20; - fallback logic means local/dev and production may behave differently if the view is absent



---



## Recommendation Dependency Summary

Confirmed recommendation dependency chain:

`/v1/recommendations/{student_id}`
→ `app/routers/recommendations.py`
→ `app.services.career_engine.compute_careers_for_student`
→ `app.services.scoring.compute_career_scores`
→ `app.services.scoring.get_student_keyskill_scores`

Confirmed DB objects involved:

- `students`
- `student_keyskill_map`
- `keyskills`
- `career_keyskill_weights_effective_int_v`
- `career_keyskill_association` (fallback)
- `careers`
- `career_clusters`

Key production-safety note:

- recommendation scoring depends on weighted keyskill data
- changes to weighted view logic, `student_keyskill_map.score`, `career_keyskill_association.weight_percentage`, or `Career.cluster` relationship may alter recommendation output

---

## Endpoint: GET /v1/questions

- **Router File:** `app/routers/questions.py`
- **Handler Function:** `get_localized_questions`
- **Mounted Path:** `/v1/questions`
- **Auth Dependency:** `get_current_user`
- **Purpose:** return localized question list for a given assessment version
- **Query Parameters:**
  - `assessment_version` (required)
  - `lang` (optional)
  - `limit`
  - `offset`
- **Confirmed Direct Reads in Router:**
  - `questions`
  - `question_facet_tags`
  - `aq_facets`
  - `facet_translations`
- **Confirmed Indirect Reads via Services:**
  - `question_translations` via `app.services.i18n_resolver.resolve_question_text`
  - `explainability_content` via `app.services.explanations.resolve_cms_text`
- **Writes:** none
- **Ordering / Pagination Behavior:**
  - questions are filtered by `questions.assessment_version`
  - ordered by `questions.id`
  - paginated via `limit` and `offset`
- **Question Text Resolution Behavior:**
  - language normalized via `normalize_lang(...)`
  - fallback order:
    1. `question_translations` for requested locale
    2. legacy language column on `questions` (`question_text_hi`, `question_text_ta`)
    3. `questions.question_text_en`
- **Facet Resolution Behavior:**
  - facet tags loaded via `question_facet_tags`
  - facet display name fallback chain:
    1. `facet_translations` for requested locale
    2. `facet_translations` for `en`
    3. `aq_facets.facet_name`
    4. `facet_id`
  - CMS override attempted using `resolve_cms_text(...)` with `explanation_key = facet_id`
  - CMS source table path: `explainability_content`
- **Response Shape Notes:**
  - `assessment_version`
  - `lang`
  - `lang_used`
  - `count_returned`
  - `questions[]`
- **Per Question Fields Observed:**
  - `question_id` (stringified)
  - `question_code`
  - `skill_id`
  - `facet_tags`
  - `question_text`
- **Frontend Contract Risk Notes:**
  - frontend likely depends on stable ordering by `id`
  - `question_id` is intentionally stringified
  - changing text fallback or facet fallback may alter student-visible output
  - language fallback behavior is part of the contract

---

## Endpoint: GET /v1/questions/pool

- **Router File:** `app/routers/questions.py`
- **Handler Function:** `get_question_pool`
- **Mounted Path:** `/v1/questions/pool`
- **Auth Dependency:** `get_current_user`
- **Purpose:** fetch question pool for runner support
- **Confirmed Direct Reads in Router:**
  - `questions`
  - `question_facet_tags`
  - `aq_facets`
  - `facet_translations`
- **Confirmed Indirect Reads via Services:**
  - `question_translations`
  - `explainability_content`
- **Writes:** none
- **Ordering Behavior:**
  - all questions ordered by `questions.id ASC`
- **Response Fields Observed:**
  - `assessment_version`
  - `lang`
  - `lang_used`
  - `count_returned`
  - `questions[]`
- **Per Question Fields Observed:**
  - `question_id`
  - `question_code`
  - `assessment_version`
  - `lang`
  - `lang_used`
  - `skill_id`
  - `facet_tags`
  - `question_text`
- **Frontend Contract Risk Notes:**
  - runner support likely depends on deterministic ordering
  - response currently sets top-level `assessment_version` to `"v1"`

---

## Endpoint: GET /v1/questions/{question_id}

- **Router File:** `app/routers/questions.py`
- **Handler Function:** `get_question_by_id`
- **Mounted Path:** `/v1/questions/{question_id}`
- **Auth Dependency:** `get_current_user`
- **Purpose:** deterministic resume-safe fetch of a single question by ID
- **Confirmed Direct Reads in Router:**
  - `questions`
  - `question_facet_tags`
  - `aq_facets`
  - `facet_translations`
- **Confirmed Indirect Reads via Services:**
  - `question_translations`
  - `explainability_content`
- **Writes:** none
- **Behavior Notes:**
  - fetch by primary key
  - uses question’s own `assessment_version`
  - localized text with fallback
- **Response Fields Observed:**
  - `question_id`
  - `question_code`
  - `assessment_version`
  - `lang`
  - `lang_used`
  - `skill_id`
  - `facet_tags`
  - `question_text`
- **Frontend Contract Risk Notes:**
  - used for resume-safe deterministic runner behavior
  - changing ID semantics, lookup behavior, or fallback logic may break resume flows

---

## Questions Router Dependency Notes

Confirmed DB objects involved across questions flow:

- `questions`
- `question_translations`
- `question_facet_tags`
- `aq_facets`
- `facet_translations`
- `explainability_content`

Important schema-risk note:

- PR-03 identified naming/version differences between local/base and production/versioned explainability objects.
- This router currently references base names such as:
  - `question_facet_tags`
  - `aq_facets`
- Production validation must confirm whether these are:
  - live tables,
  - compatibility views,
  - or local-only assumptions.



## Recommendation Dependency Summary

Confirmed recommendation dependency chain:

`/v1/recommendations/{student_id}`
→ `app/routers/recommendations.py`
→ `app.services.career_engine.compute_careers_for_student`
→ `app.services.scoring.compute_career_scores`
→ `app.services.scoring.get_student_keyskill_scores`

Confirmed DB objects involved:

- `students`
- `student_keyskill_map`
- `keyskills`
- `career_keyskill_weights_effective_int_v`
- `career_keyskill_association` (fallback)
- `careers`
- `career_clusters`

Key production-safety note:

- recommendation scoring depends on weighted keyskill data
- changes to weighted view logic, `student_keyskill_map.score`, `career_keyskill_association.weight_percentage`, or `Career.cluster` relationship may alter recommendation output

---

## Endpoint: POST /v1/assessments/

- **Router File:** `app/routers/assessments.py`
- **Handler Function:** `create_assessment`
- **Mounted Path:** `/v1/assessments/`
- **Auth Dependency:** `get_current_active_user`
- **Purpose:** start a new assessment session
- **Confirmed Writes:**
  - `assessments`
  - `context_profile` (via `_ensure_context_profile_for_assessment`)
  - `assessment_questions`
- **Confirmed Reads:**
  - `students` (to resolve `students.id` from `students.user_id`)
  - `questions`
  - `question_facet_tags_v`
  - `aq_facets_v`
- **Sampling Logic Notes:**
  - assessment shell is created with pinned versions:
    - `assessment_version = "v1"`
    - `scoring_config_version = "v1"`
    - `question_pool_version = "v1"`
  - question sampler `_sample_75_questions_v1(...)` uses SQL with:
    - `questions`
    - `question_facet_tags_v`
    - `aq_facets_v`
  - expected output is exactly `75` questions
  - sampler uses `ROW_NUMBER() OVER (PARTITION BY aq_code ORDER BY RANDOM())`
  - 3 questions are selected per AQ bucket
- **Context Profile Behavior:**
  - automatically ensures one `context_profile` row per assessment
  - placeholder/default values used if missing
  - computes and persists `cps_score`
- **Writes Behavior Notes:**
  - `assessment_questions` is persisted as the canonical question set for the assessment
  - persistence is idempotent if rows already exist for that assessment
- **Frontend Contract Risk Notes:**
  - frontend assessment flow depends on assessment creation returning a valid assessment shell
  - resume/submission flow depends on canonical `assessment_questions` existing
  - changing version pinning, question count, or question pool generation behavior may break downstream assessment flow

---

## Endpoint: POST /v1/assessments/{assessment_id}/responses

- **Router File:** `app/routers/assessments.py`
- **Handler Function:** `submit_responses`
- **Mounted Path:** `/v1/assessments/{assessment_id}/responses`
- **Auth Dependency:** `get_current_active_user`
- **Purpose:** append immutable response batch and return resume pointer
- **Confirmed Reads:**
  - `assessments`
  - `assessment_answer_scale`
  - `assessment_responses`
  - `assessment_questions`
  - `questions`
  - `assessment_results` (to avoid duplicate background result generation)
- **Confirmed Writes:**
  - `assessment_responses`
- **Validation / Gate Behavior:**
  - verifies assessment exists and belongs to current user
  - rejects empty batch
  - resolves canonical answer scale using assessment’s `assessment_version`
  - validates `question_id` format
  - validates question exists in `questions`
  - validates question belongs to this assessment’s canonical pool from `assessment_questions`
  - validates `question_code` if provided by client
  - validates numeric answer range using `assessment_answer_scale`
- **Idempotency / Replay Behavior:**
  - respects `idempotency_key` if provided
  - skips already-existing submitted question_ids for offline replay safety
  - handles race-safe replay through integrity error recovery
- **Resume Pointer Behavior:**
  - computes:
    - `answered_count`
    - `last_answered_question_id`
    - `next_question_id`
    - `total_questions`
    - `is_complete`
  - primary source of truth for question order is `assessment_questions`
  - legacy fallback uses global `questions.id` ordering if no persisted pool exists
- **Background Side Effect:**
  - if `assessment_results` row does not exist, schedules background task:
    - `generate_result(assessment_id, current_user.id)`
- **Frontend Contract Risk Notes:**
  - runner/resume flow depends on deterministic question progression
  - `next_question_id` logic depends on stable `assessment_questions` order
  - immutability and idempotency behavior are part of the contract for offline/replay-safe submission
  - changing answer validation or pool-membership enforcement may affect mobile/frontend replay flows

---

## Assessments Router Notes — Part 1

Confirmed DB objects involved so far:

- `assessments`
- `students`
- `context_profile`
- `questions`
- `question_facet_tags_v`
- `aq_facets_v`
- `assessment_questions`
- `assessment_answer_scale`
- `assessment_responses`
- `assessment_results`

Important dependency notes:

- assessment creation uses versioned question-bucketing objects:
  - `question_facet_tags_v`
  - `aq_facets_v`
- response submission uses `assessment_questions` as the canonical pool source of truth
- this router is a central dependency point for:
  - assessment creation
  - immutable answer persistence
  - resume flow
  - later scoring/result generation


---

## Endpoint: POST /v1/assessments/{assessment_id}/submit-assessment

- **Router File:** `app/routers/assessments.py`
- **Handler Function:** `submit_assessment`
- **Mounted Path:** `/v1/assessments/{assessment_id}/submit-assessment`
- **Auth Dependency:** `get_current_active_user`
- **Purpose:** finalize assessment answers and compute persisted scores, tiers, analytics, and recommendation result payloads

- **Confirmed Direct Reads in Router:**
  - `assessments`
  - `assessment_responses`
  - `assessment_questions`
  - `assessment_answer_scale`
  - `context_profile`
  - `students`
  - `student_skill_scores`
  - `assessment_results`

- **Confirmed Indirect Reads via Services:**
  - `question_student_skill_weights` via `app.services.assessment_scoring_service.compute_and_persist_skill_scores`
  - `student_keyskill_map` via `sync_skill_scores_to_keyskills(...)` and recommendation scoring path
  - `career_keyskill_weights_effective_int_v` via recommendation scoring path
  - `career_keyskill_association` as fallback in scoring path
  - `careers`
  - `career_clusters`

- **Confirmed Writes:**
  - `student_skill_scores`
  - `student_keyskill_map`
  - `assessment_results`

- **Scoring Pipeline Notes:**
  - validates persisted response membership against `assessment_questions`
  - re-validates canonical answer scale using `assessment_answer_scale`
  - computes and persists skill scores through `compute_and_persist_skill_scores(...)`
  - QSSW source of truth is `question_student_skill_weights`
  - missing QSSW mappings cause explicit error (`MissingQSSWError`)
  - syncs skill scores to keyskills through `sync_skill_scores_to_keyskills(...)`
  - recomputes analytics through `recompute_student_analytics(...)`
  - computes career recommendations through `compute_careers_for_student(...)`
  - persists final student-safe result bundle into `assessment_results`

- **QSSW / Skill Score Logic Notes (confirmed from `assessment_scoring_service.py`):**
  - persisted responses are read from `assessment_responses`
  - scoring uses canonical numeric `answer_value`, falling back to raw `answer` if needed
  - response values are enforced on canonical scale `1..5`
  - skill contributions are computed from `question_student_skill_weights`
  - weights are normalized per question before contribution aggregation
  - per-skill outputs persisted into `student_skill_scores` include:
    - `raw_total`
    - `question_count`
    - `avg_raw`
    - `scaled_0_100`
  - stale `student_skill_scores` rows for removed skills are deleted for the same assessment/config version
  - scoring return payload also includes deterministic `contrib_trace_seed`

- **Context / HSI Notes:**
  - CPS score is loaded from `context_profile`
  - HSI is computed via `compute_hsi_v1(...)`
  - HSI fields are persisted back into `student_skill_scores`
  - current beta tier policy still uses `scaled_0_100`, not HSI, for tier assignment

- **KeySkill Sync Notes:**
  - `sync_skill_scores_to_keyskills(...)` reads:
    - `student_skill_scores`
    - `skill_keyskill_map`
    - `students`
  - writes:
    - `student_keyskill_map`
  - mapping logic:
    - loads `student_skill_scores` for the given `assessment_id` + `scoring_config_version`
    - maps `users.id` to `students.id` via `students.user_id`
    - loads `skill_keyskill_map` rows for scored skills
    - computes weighted average of `scaled_0_100` per keyskill
    - upserts into `student_keyskill_map` by `(student_id, keyskill_id)`
  - deterministic behavior:
    - if no `student_skill_scores` exist, sync exits safely
    - if no `students` row exists for the mapped user, sync exits safely
    - if no `skill_keyskill_map` rows exist, nothing is written
  - backend dependency note:
    - `skill_keyskill_map` is a confirmed dependency in local scoring flow and should be treated as part of the submit-assessment dependency chain

- **Analytics Orchestrator Notes:**
  - `recompute_student_analytics(...)` reads:
    - `students`
    - `student_keyskill_map`
  - writes:
    - `student_analytics_summary`
  - orchestration logic:
    - expects `student_id = students.id`
    - verifies student exists
    - reads all `student_keyskill_map` rows for that student
    - computes deterministic dashboard summary payload
    - computes:
      - distribution buckets (`low`, `medium`, `high`)
      - top keyskills
      - overall summary (`count`, `avg_score`, `top_n`)
    - upserts one snapshot row into `student_analytics_summary` by `(student_id, scoring_config_version)`
  - deterministic behavior:
    - if no `student_keyskill_map` rows exist, returns safely with no exception
    - if snapshot upsert fails, rolls back and records warning
  - backend dependency note:
    - `student_analytics_summary` is a confirmed write dependency in the submit-assessment internal pipeline


- **Recommendation Integration Notes:**
  - recommendation payload is computed using the same unified recommendation engine as `/v1/recommendations/...`
  - student-safe sanitization is applied before persisting `recommended_careers` into `assessment_results`

- **Response Contract Notes:**
  - student response returns:
    - `assessment_id`
    - `tiers`
  - admin/counsellor response returns:
    - `assessment_id`
    - `skill_scores`
    - `tiers`

- **Frontend Contract Risk Notes:**
  - this is the core scoring endpoint of the platform
  - changes to `question_student_skill_weights`, `student_skill_scores`, `student_keyskill_map`, weighted career view logic, or result persistence may affect scoring and final recommendation output
  - student/admin response shapes differ and must remain unchanged


---

## Endpoint: GET /v1/assessments/active

- **Router File:** `app/routers/assessments.py`
- **Handler Function:** `get_active_assessment`
- **Mounted Path:** `/v1/assessments/active`
- **Auth Dependency:** `get_current_active_user`
- **Response Model:** `app.schemas_resume.ActiveAssessmentResponse`
- **Purpose:** fetch the latest active assessment state for resume-safe frontend runner flow

- **Confirmed Reads:**
  - `assessments`
  - `assessment_results`
  - `assessment_questions`
  - `assessment_responses`
  - `questions` (legacy fallback path only)

- **Writes:** none

- **Selection Logic Notes:**
  - primary rule:
    - latest assessment for current user where no `assessment_results` row exists
  - fallback rule:
    - latest assessment for current user even if partially answered
  - if no assessment exists:
    - returns `active=False` payload, not an error

- **Resume Logic Notes:**
  - canonical question order source is `assessment_questions`
  - `answered_count` comes from `assessment_responses`
  - `last_answered_question_id` is derived from latest persisted response row
  - `next_question_id` is derived deterministically from ordered `assessment_questions`
  - if no persisted question set exists, legacy fallback uses global `questions.id` ordering
  - `is_complete` is computed from `next_question_id is None` and `answered_count >= total_questions`

- **Confirmed Response Contract Fields (from `ActiveAssessmentResponse`):**
  - `active`
  - `assessment_id`
  - `assessment_version`
  - `scoring_config_version`
  - `question_pool_version`
  - `answered_count`
  - `last_answered_question_id`
  - `next_question_id`
  - `total_questions`
  - `is_complete`

- **Frontend Contract Risk Notes:**
  - this endpoint is critical for resume-safe assessment UX
  - frontend likely depends on exact field names and nullable behavior
  - changing active-assessment selection logic may break resume handling
  - changing question ordering source may break deterministic runner behavior

---


## Endpoint: GET /v1/assessments/{assessment_id}/questions

- **Router File:** `app/routers/assessments.py`
- **Handler Function:** `get_assessment_questions`
- **Mounted Path:** `/v1/assessments/{assessment_id}/questions`
- **Auth Dependency:** `get_current_active_user`
- **Response Model:** `app.schemas_assessment_questions.AssessmentQuestionsResponse`
- **Purpose:** fetch the exact canonical assessment-bound question set in student-safe format

- **Confirmed Reads:**
  - `assessments`
  - `assessment_questions`
  - `questions`
  - `question_facet_tags`

- **Writes:** none

- **Access Control Notes:**
  - admin can access any assessment
  - student can access only their own assessment
  - non-owner student receives `404` rather than existence-leaking error

- **Question Set Logic Notes:**
  - canonical source of truth is `assessment_questions`
  - deterministic ordering is `assessment_questions.question_id`
  - all related `questions` rows are batch-loaded by `question_id`
  - facet tags are batch-loaded from `question_facet_tags`
  - if no assessment-bound questions exist, returns an empty response model, not an error

- **Language / Text Logic Notes:**
  - localized text is resolved from language-specific columns on `questions`
  - supported field map in this handler:
    - `en -> question_text_en`
    - `hi -> question_text_hi`
    - `ta -> question_text_ta`
  - unsupported languages fall back to English
  - empty/missing localized text also falls back to English
  - `lang_used` reflects actual language returned

- **Confirmed Response Contract Fields (from `AssessmentQuestionsResponse`):**
  - `assessment_version`
  - `lang`
  - `lang_used`
  - `count_returned`
  - `questions`

- **Per Question Contract Fields (from `AssessmentQuestionItemOut`):**
  - `question_id` (string)
  - `question_code`
  - `skill_id`
  - `question_text`
  - `facet_tags`

- **Frontend Contract Risk Notes:**
  - this endpoint is critical for assessment runner consistency
  - frontend likely depends on deterministic ordering and exact field names
  - `question_id` is intentionally returned as string
  - changing canonical source from `assessment_questions` may break resume-safe behavior
  - note that this handler uses base table `question_facet_tags`, while other assessment creation logic uses `question_facet_tags_v`

---

## Endpoint: GET /v1/assessments/{assessment_id}

- **Router File:** `app/routers/assessments.py`
- **Handler Function:** `get_assessment`
- **Mounted Path:** `/v1/assessments/{assessment_id}`
- **Auth Dependency:** `get_current_active_user`
- **Response Model:** `AssessmentOut` (from `app/schemas_legacy.py`, imported via `app.schemas`)
- **Purpose:** fetch assessment shell / pinned assessment session metadata

- **Confirmed Reads:**
  - `assessments`

- **Writes:** none

- **Access Control Notes:**
  - assessment must belong to current user
  - non-owner access returns `404`

- **Confirmed Response Contract Fields (from `AssessmentOut`):**
  - `id`
  - `user_id`
  - `submitted_at`
  - `assessment_version`
  - `scoring_config_version`
  - `question_pool_version`

- **Frontend Contract Risk Notes:**
  - this endpoint exposes pinned assessment session metadata
  - changing version fields or ownership behavior may affect frontend session continuity

---

## Endpoint: GET /v1/assessments/{assessment_id}/result

- **Router File:** `app/routers/assessments.py`
- **Handler Function:** `get_result`
- **Mounted Path:** `/v1/assessments/{assessment_id}/result`
- **Auth Dependency:** `get_current_active_user`
- **Response Model:** `AssessmentResultOut` (from `app/schemas_legacy.py`, imported via `app.schemas`)
- **Purpose:** fetch the computed assessment result bundle for a completed assessment

- **Confirmed Reads:**
  - `assessment_results`
  - `assessments` (indirectly via ORM relationship `result.assessment.user_id`)

- **Writes:** none

- **Access Control Notes:**
  - result must exist
  - associated assessment must belong to current user
  - if result is missing or inaccessible, returns `404` with `Result not ready`

- **Result Payload Notes:**
  - `recommended_careers` is expected as JSON/list
  - if stored as string, handler splits it into list for compatibility
  - endpoint returns computed tiers and recommendation payload, not raw scoring internals

- **Confirmed Response Contract Fields (from `AssessmentResultOut`):**
  - `assessment_id`
  - `recommended_stream`
  - `recommended_careers`
  - `skill_tiers`
  - `generated_at`

- **Frontend Contract Risk Notes:**
  - frontend likely depends on this endpoint for post-assessment result rendering
  - changing recommendation payload shape or tier structure may break result pages
  - compatibility handling for string-vs-list `recommended_careers` should be preserved unless fully migrated safely

---

## Endpoint: GET /v1/paid-analytics/{student_id}

- **Router File:** `app/routers/paid_analytics.py`
- **Handler Function:** `get_paid_analytics`
- **Mounted Path:** `/v1/paid-analytics/{student_id}`
- **Auth Dependency:** `require_admin_or_counsellor`
- **Response Model:** `PaidAnalyticsResponse` (from `app/schemas_legacy.py`, imported via `app.schemas`)
- **Purpose:** return premium weighted analytics with numeric cluster/career/keyskill score maps plus CMS-driven explanations

- **Confirmed Reads:**
  - `student_keyskill_map`
  - `careers`
  - `career_clusters`
  - `career_keyskill_weights_effective_int_v`
  - `career_keyskill_association` (fallback path in scoring)
  - `keyskills`
  - `students`
  - `explainability_content`

- **Writes:** none

- **Service Dependency Path:**
  - `get_student_keyskill_scores(...)`
  - `compute_career_scores(...)`
  - `compute_cluster_scores(...)`
  - `build_full_explanation(...)`

- **Explanation Builder Dependency Notes:**
  - `build_full_explanation(...)` reads:
    - `careers`
    - `career_clusters`
    - `keyskills`
    - `student_keyskill_map`
    - `career_keyskill_association`
    - `explainability_content`
  - explanation text is resolved through CMS keys using `resolve_cms_text(...)`

- **Response Behavior Notes:**
  - if no student keyskills exist, returns empty analytics payload with message
  - includes numeric:
    - `cluster_scores`
    - `career_scores`
    - `keyskill_scores`
  - includes explanation-rich:
    - `clusters`
    - `careers`

- **Frontend Contract Risk Notes:**
  - numeric score maps are part of admin/counsellor contract here
  - any change to weighted scoring objects or CMS explanation resolution may affect analytics dashboards
  - fallback behavior when no keyskills exist should remain unchanged

---

## Endpoint: GET /v1/paid-analytics/{student_id}/student

- **Router File:** `app/routers/paid_analytics.py`
- **Handler Function:** `get_paid_analytics_student`
- **Mounted Path:** `/v1/paid-analytics/{student_id}/student`
- **Auth Dependency:** `require_role("student")`
- **Response Model:** `PaidAnalyticsStudentResponse` (from `app/schemas_legacy.py`, imported via `app.schemas`)
- **Purpose:** return student-safe paid analytics without numeric scores, weights, or percentages

- **Confirmed Reads:**
  - `student_keyskill_map`
  - `careers`
  - `career_clusters`
  - `career_keyskill_association`
  - `keyskills`
  - `explainability_content`

- **Writes:** none

- **Service Dependency Path:**
  - `get_student_keyskill_scores(...)`
  - `build_full_explanation(...)`

- **Student-Safe Behavior Notes:**
  - `allow_numbers_in_text=False` is passed into CMS explanation resolution
  - numeric score fields are not returned
  - response contains only:
    - fit bands
    - top keyskills
    - explanation blocks
  - if no student keyskills exist, returns empty student-safe payload with message

- **Response Contract Risk Notes:**
  - student-safe projection must remain non-numeric
  - changes to explanation block shape, fit_band keys, or top_keyskills fields may break student-facing premium views

---

## Endpoint: GET /v1/paid-analytics/{student_id}/deep

- **Router File:** `app/routers/paid_analytics.py`
- **Handler Function:** `get_paid_analytics_deep_insights`
- **Mounted Path:** `/v1/paid-analytics/{student_id}/deep`
- **Auth Dependency:** `require_roles("admin", "counsellor", "student")`
- **Response Model:** inline dict response (no dedicated schema shown in router)
- **Purpose:** return deep-insight explanation keys for frontend/CMS resolution, not final prose

- **Confirmed Reads:**
  - `student_keyskill_map`
  - `careers`
  - `career_clusters`
  - `career_keyskill_association`
  - `keyskills`
  - `explainability_content`

- **Writes:** none

- **Behavior Notes:**
  - reuses `build_full_explanation(...)`
  - returns explanation keys only
  - frontend is expected to resolve final text through `/v1/content/explainability`
  - response includes:
    - `cluster_insights`
    - `career_insights`
    - `next_steps`
  - evidence arrays are currently empty placeholders in this MVP path

- **Frontend Contract Risk Notes:**
  - this endpoint appears designed as a CMS-key contract, not prose contract
  - changing key names or response nesting may break frontend key-resolution logic

---

## Paid Analytics Router Notes

Confirmed DB objects involved across paid analytics flow:

- `student_keyskill_map`
- `careers`
- `career_clusters`
- `career_keyskill_weights_effective_int_v`
- `career_keyskill_association`
- `keyskills`
- `students`
- `explainability_content`

Important dependency notes:

- admin/counsellor paid analytics path returns numeric score maps
- student paid analytics path must remain non-numeric
- deep insights path is key-driven and depends on frontend/CMS resolution rather than backend-rendered prose

---

## Endpoint: GET /v1/content/explainability



- **Router File:** `app/routers/content.py`
- **Handler Function:** `get_explainability_content`
- **Mounted Path:** `/v1/content/explainability`
- **Auth Dependency:** none visible in router
- **Response Model:** `ExplainabilityContentResponse` (from `app/schemas_legacy.py`, imported via `app.schemas`)
- **Purpose:** return public, student-safe explainability CMS content for a given version/locale, with optional key filtering

- **Confirmed Reads:**
  - `explainability_content`

- **Writes:** none

- **Query Parameters:**
  - `version`
  - `locale`
  - `lang` (alias for locale)
  - `keys` (comma-separated explanation keys)
  - `facet_keys` (repeatable and/or comma-separated)
  - `aq_keys` (repeatable and/or comma-separated)

- **Content Resolution Notes:**
  - locale is normalized via `normalize_lang(...)`
  - requested locale is fetched first
  - English fallback is fetched when requested locale is not `en`
  - merge logic:
    - English fills gaps
    - requested locale overrides English for matching keys
  - only active rows are returned (`is_active = True`)

- **Key Expansion Notes:**
  - `facet_keys` are expanded into:
    - `FACET.{TOKEN}.001`
    - `FACET.{TOKEN}.LABEL`
    - `FACET.{TOKEN}.DESC`
  - `aq_keys` are expanded into:
    - `AQ.{TOKEN}.001`
    - `AQ.{TOKEN}.LABEL`
    - `AQ.{TOKEN}.DESC`
  - direct `keys` filter is also supported
  - final key list is de-duplicated while preserving stable order

- **Confirmed Response Contract Fields:**
  - `version`
  - `locale`
  - `items`

- **Per Item Contract Fields:**
  - `explanation_key`
  - `text`

- **Frontend Contract Risk Notes:**
  - this endpoint is the CMS/key-resolution dependency for deep insights and explainability flows
  - changing key expansion patterns or locale fallback behavior may break frontend content resolution
  - public/student-safe behavior should remain non-analytic and non-numeric


## Endpoint: GET /v1/students/{student_id}/dashboard

---

- **Router File:** `app/routers/student_dashboard.py`
- **Handler Function:** `get_student_dashboard`
- **Mounted Path:** `/v1/students/{student_id}/dashboard`
- **Auth Dependency:** `get_current_active_user`
- **Response Model:** `StudentDashboardResponse` (from `app/schemas_legacy.py`, imported via `app.schemas`)
- **Purpose:** return student dashboard aggregation including assessment KPIs, analytics snapshot preview, and top skills

- **Confirmed Reads:**
  - `students`
  - `assessments`
  - `student_analytics_summary`
  - `student_skill_scores`

- **Writes:** none

- **Access Control Notes:**
  - student must exist
  - ownership enforced through `students.user_id == current_user.id`
  - non-owner access returns `403`

- **Aggregation Logic Notes:**
  - `total_assessments` is computed from `assessments.user_id`
  - latest assessment is selected by `assessments.submitted_at DESC`
  - if no assessments exist, returns deterministic empty dashboard response with message `"No assessments yet"`

- **Analytics Snapshot Consumption Notes:**
  - preferred source is `student_analytics_summary`
  - filtered by:
    - `student_id`
    - `scoring_config_version = "v1"`
  - `payload_json` is passed through `project_student_safe(...)`
  - dashboard extracts:
    - `overall_keyskill_summary`
    - `distribution`
    - `top_keyskills`

- **Top Skills Notes:**
  - sourced from latest assessment’s `student_skill_scores`
  - filtered by:
    - `assessment_id = last_assessment.id`
    - `scoring_config_version = "v1"`
  - ordered by:
    - `scaled_0_100 DESC`
    - `skill_id`
  - limited to top 10
  - `scaled_0_100` is intentionally returned as `None` in response projection
  - `tier` is included if present on stored rows

- **Confirmed Response Contract Fields (from `StudentDashboardResponse`):**
  - `student_id`
  - `scoring_config_version`
  - `assessment_kpis`
  - `keyskill_analytics`
  - `top_skills`
  - `message`

- **Frontend Contract Risk Notes:**
  - this endpoint depends on `student_analytics_summary` as the preferred snapshot source
  - changing snapshot payload structure may break dashboard rendering
  - dashboard intentionally projects top skills without exposing numeric `scaled_0_100`
  - ownership and empty-state behavior should remain unchanged

