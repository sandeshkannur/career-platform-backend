# PR-08 Explainability Flow Validation

## Objective
Validate question -> facet -> associated quality / explanation flow without changing business behavior, scoring semantics, admin workflow, or frontend API contracts.

## PR Metadata
- PR ID: PR-08
- PR Name: Explainability Flow Validation
- Type: Validation
- Scope / Concern: Validate AQ explainability pipeline
- DB Objects: aq_facets_v, associated_qualities_v
- APIs (Additive Only): None
- Validation Artifact: explainability_validation.md

---

## In-Scope Objects
- associated_qualities_v
- aq_facets_v
- question_facet_tags_v
- questions

---

## What Was Preserved
- Assessment flow behavior
- Scoring pipeline behavior
- Student-facing text-only output
- Existing frontend-linked response contracts
- Free vs premium behavior
- Role-based visibility
- Admin upload workflow

---

## Validation Performed

### 1. Schema Presence
Confirmed:
- associated_qualities_v exists
- aq_facets_v exists
- question_facet_tags_v exists
- questions exists

### 2. Object Type / Structure
Confirmed:
- associated_qualities_v is a VIEW
- aq_facets_v is a VIEW
- question_facet_tags_v is a VIEW
- questions is a BASE TABLE

Confirmed actual join columns:
- questions.assessment_version + questions.question_code
- question_facet_tags_v.assessment_version + question_facet_tags_v.question_code
- question_facet_tags_v.assessment_version + question_facet_tags_v.facet_code
- aq_facets_v.assessment_version + aq_facets_v.facet_code
- aq_facets_v.assessment_version + aq_facets_v.aq_code
- associated_qualities_v.assessment_version + associated_qualities_v.aq_code

### 3. Data Integrity
Validated:
- questions_without_facet_mapping = 0
- orphan question mappings = 0
- orphan facet mappings = 0
- orphan AQ links = 0
- duplicate question-facet mappings = 0

### 4. Coverage
Validated counts:
- associated_qualities_v = 25
- aq_facets_v = 123
- question_facet_tags_v = 675
- questions = 675

Coverage summary:
- total_questions = 675
- mapped_questions = 675
- mapped_facets = 675
- mapped_aqs = 675

### 5. End-to-End Trace
Sample rows confirm:
question_code -> facet_code -> aq_code -> facet_name_en -> aq_name_en

Examples observed:
- AQ01_F1_Q001 -> AQ01_F1 -> AQ_01 -> Exploratory Openness -> Curiosity Drive
- AQ02_F1_Q001 -> AQ02_F1 -> AQ_02 -> Problem Clarification -> Inquiry Framing

### 6. Backend Runtime Usage
Backend search confirms runtime usage already exists in:
- app/services/evidence.py
- app/routers/assessments.py
- app/routers/admin.py

Notably, evidence.py explicitly documents:
assessment_responses -> questions -> question_facet_tags_v -> aq_facets_v -> associated_qualities_v

---

## Findings

### Schema
The versioned explainability pipeline exists and is implemented using VIEW-based objects keyed by:
- assessment_version
- question_code
- facet_code
- aq_code

### Data Integrity
No integrity issues were found in the validated versioned flow.

### Runtime Usage
The explainability path is already wired into backend evidence generation and related assessment/admin code paths.

### End-to-End Flow Status
Working

---

## Gap Analysis
No explainability gap was found in the versioned AQ pipeline.

The initial failed SQL assumptions were due to using incorrect id-based joins. Actual production/runtime explainability flow is code-based and version-aligned.

One minor observation:
- some legacy/base-table validation code appears to reference facet_id-style joins and should be treated as a separate future hardening review, not a PR-08 blocker.

---

## Change Requirement Decision
- No backend change required

---

## API / Frontend Contract Impact Check
- No API change required
- No frontend contract change required

---

## Risk Level
Low

Reason:
The explainability flow is already present, populated, and correctly linked end-to-end.

---

## Production Safety Decision
- No migration required
- No logic change required
- No schema change required

---

## Explicitly Not Changed
- Free vs premium behavior
- Question randomization
- Assessment creation/resume behavior
- Scoring pipeline
- Student-facing output contract
- Existing API response shapes
- Role-based access behavior
- Admin ingestion workflow

---

## Final Conclusion
PR-08 validation is successful.

The AQ explainability pipeline is already implemented and functioning correctly through the versioned flow:
questions -> question_facet_tags_v -> aq_facets_v -> associated_qualities_v

No backend, schema, API, or migration change is required for PR-08.
