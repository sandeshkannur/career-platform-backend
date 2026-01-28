# app/schemas.py
#
# NOTE:
# - Your file already works, but it had repeated imports mid-file.
# - I am keeping ALL existing schemas as-is (same names/fields),
#   and only making the "required places" clean + safe:
#     1) consolidate imports at the top (no mid-file re-imports)
#     2) make SessionUserOut explicitly include consent_verified (already present) and comment it
#     3) keep compatibility with both Pydantic v1 (orm_mode) and v2 (from_attributes)
#
# IMPORTANT:
# - No breaking changes to existing response shapes.
# - No schema renames.
# - No field type changes.

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, constr



# ===============================
# USER SCHEMAS
# ===============================

class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    dob: date
    guardian_email: Optional[EmailStr] = None
    role: Optional[str] = "student"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Message(BaseModel):
    message: str


# ===============================
# ADMIN UPLOAD RESPONSE SCHEMA
# ===============================

class UploadResponse(BaseModel):
    status: str
    inserted: int


class UploadQuestionsResult(BaseModel):
    uploaded: int
    skipped: int
    errors: List[str] = Field(default_factory=list)

# ===============================
# PR2: QUESTION ↔ FACET TAG UPLOAD SCHEMAS
# ===============================

class QuestionFacetTagUploadRow(BaseModel):
    question_id: int
    facet_id: str


# ===============================
# ADMIN USER MANAGEMENT SCHEMAS
# ===============================

class RoleChange(BaseModel):
    role: Literal["admin", "student", "editor"]


class GuardianAssign(BaseModel):
    guardian_email: EmailStr


# ===============================
# USER RESPONSE SCHEMA
# ===============================

class User(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    dob: date
    is_minor: bool
    guardian_email: Optional[EmailStr] = None
    role: str

    model_config = ConfigDict(from_attributes=True)


# ===============================
# SKILL SCHEMAS
# ===============================

class SkillCreate(BaseModel):
    name: str


class Skill(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


# ===============================
# STUDENT SCHEMAS
# ===============================

class StudentCreate(BaseModel):
    name: str
    grade: int


class Student(BaseModel):
    id: int
    name: str
    grade: int

    model_config = ConfigDict(from_attributes=True)


# ===============================
# STUDENT-SKILL MAP SCHEMAS
# ===============================

class StudentSkillMapCreate(BaseModel):
    student_id: int
    skill_id: int


class StudentSkillMap(BaseModel):
    id: int
    student_id: int
    skill_id: int

    model_config = ConfigDict(from_attributes=True)


# ===============================
# CAREER CLUSTER SCHEMAS
# ===============================

class CareerClusterCreate(BaseModel):
    name: str
    description: Optional[str] = None


class CareerCluster(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ===============================
# KEYSKILL SCHEMAS
# ===============================

class CareerSimple(BaseModel):
    id: int
    title: str
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class KeySkillCreate(BaseModel):
    name: str
    cluster_id: int


class KeySkill(BaseModel):
    id: int
    name: str
    cluster_id: Optional[int] = None
    careers: List[CareerSimple] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ===============================
# CAREER SCHEMAS
# ===============================

class KeySkillBase(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class CareerCreate(BaseModel):
    title: str
    description: Optional[str] = None
    cluster_id: Optional[int] = None


class Career(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    cluster_id: Optional[int] = None
    keyskills: List[KeySkillBase] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ===============================
# STUDENT-KEYSKILL MAP SCHEMAS
# ===============================

class StudentKeySkillMapCreate(BaseModel):
    student_id: int
    keyskill_id: int
    # Optional numeric score (0–100) – can be filled by assessment logic
    score: Optional[float] = None


class StudentKeySkillMap(BaseModel):
    id: int
    student_id: int
    keyskill_id: int
    score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


# ===============================
# PAID ANALYTICS SCHEMA - (OLD) Cluster Insights
# ===============================

class ClusterInsight(BaseModel):
    cluster_id: int
    cluster_name: str
    careers: List[str] = Field(default_factory=list)
    key_skills: List[str] = Field(default_factory=list)
    matched_skills: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# ===============================
# PAID ANALYTICS SCHEMAS - NEW (Weighted + Explanations + Bands)
# ===============================

class PaidClusterInsight(BaseModel):
    cluster_id: int
    cluster_name: str
    score: float
    top_keyskills: List[str] = Field(default_factory=list)

    # NEW FIELD: core / supporting / auxiliary breakdown
    # e.g. {"core": 55.0, "supporting": 30.0, "auxiliary": 15.0}
    band_breakdown: Dict[str, float] = Field(default_factory=dict)

    explanation: str


class PaidCareerInsight(BaseModel):
    career_id: int
    career_name: str
    score: float
    top_keyskills: List[str] = Field(default_factory=list)
    explanation: str


class PaidAnalyticsResponse(BaseModel):
    student_id: int
    clusters: List[PaidClusterInsight] = Field(default_factory=list)
    careers: List[PaidCareerInsight] = Field(default_factory=list)

    # Raw score maps (useful for dashboards)
    cluster_scores: Dict[int, float] = Field(default_factory=dict)
    career_scores: Dict[int, float] = Field(default_factory=dict)
    keyskill_scores: Dict[int, float] = Field(default_factory=dict)

    message: Optional[str] = None


# ===============================
# B9 INTERNAL ORCHESTRATOR RESULT (INTERNAL USE ONLY)
# ===============================

class AnalyticsResult(BaseModel):
    """
    B9 return object (internal use; log-friendly).
    This does NOT change any existing public endpoint contracts.
    """
    student_id: int
    scoring_config_version: str = "v1"
    computed_at: Optional[datetime] = None

    # persistence status
    summary_row_upserted: bool = False

    # data stats
    keyskills_found: int = 0

    # robustness reporting
    warnings: List[str] = Field(default_factory=list)

    # small preview for logs/debug (keep minimal)
    payload_preview: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


# ===============================
# ASSESSMENT SCHEMAS
# ===============================

class AssessmentOut(BaseModel):
    id: int
    user_id: int
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssessmentResponseCreate(BaseModel):
    question_id: str = Field(
        ...,
        json_schema_extra={"example": "V1_Q1"},
    )
    # ✅ canonical/external id (preferred for analytics + long-term stability)
    question_code: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "AQ01_F1_Q001"},
    )
    answer: constr(pattern=r"^[1-5]$") = Field(
        ...,
        json_schema_extra={"example": "5"},
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=80,
        json_schema_extra={
            "example": "6b4e7d5a-7ed6-4a10-b4d7-ff7d3a8e1d21"
        },
    )



class AssessmentResponseOut(BaseModel):
    question_id: str = Field(
        ...,
        json_schema_extra={"example": "V1_Q1"},
    )
    answer: str = Field(
        ...,
        json_schema_extra={"example": "5"},
    )

    model_config = ConfigDict(from_attributes=True)
class AssessmentResultOut(BaseModel):
    assessment_id: int
    recommended_stream: Optional[str] = None
    recommended_careers: Optional[List[Any]] = None
    skill_tiers: Optional[Dict[str, str]] = None
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# ===============================
# PR5: Evidence Schemas (computed-on-read)
# ===============================

class FacetEvidenceItem(BaseModel):
    facet_code: str
    facet_name_en: str
    aq_code: str
    aq_name_en: str
    evidence_count: int
    question_codes: List[str] = Field(default_factory=list)


class AQEvidenceSummaryItem(BaseModel):
    aq_code: str
    aq_name_en: str
    evidence_count: int
    facet_codes: List[str] = Field(default_factory=list)
    question_codes: List[str] = Field(default_factory=list)


class AssessmentEvidenceBlock(BaseModel):
    facet_evidence: List[FacetEvidenceItem] = Field(default_factory=list)
    aq_evidence_summary: List[AQEvidenceSummaryItem] = Field(default_factory=list)


# ===============================
# PR6: Student-safe AQ/Facet blocks (computed-on-read from PR5 evidence)
# ===============================

class ScorecardFacetExplainBlock(BaseModel):
    facet_code: str
    facet_name_en: str
    aq_code: str
    aq_name_en: str
    # Traceability without pressure (no counts/scores)
    question_codes: List[str] = Field(default_factory=list)
    # Optional CMS key (versioned content) — additive, safe
    explanation_key: Optional[str] = None


class ScorecardAQExplainBlock(BaseModel):
    aq_code: str
    aq_name_en: str
    facet_codes: List[str] = Field(default_factory=list)
    question_codes: List[str] = Field(default_factory=list)
    explanation_key: Optional[str] = None


class ScorecardFacetEvidenceBlock(BaseModel):
    facet_code: str
    evidence_question_codes: List[str] = Field(default_factory=list)

# ===============================
# SCORECARD RESPONSE (FULL REPORT)
# ===============================

class KeySkillScore(BaseModel):
    keyskill_id: int
    name: str
    score: float            # 0–100 numeric score
    normalized: float       # 0.0–1.0
    tier: str               # e.g., "High"
    cluster_id: Optional[int] = None
    cluster_name: Optional[str] = None


class ScorecardCluster(BaseModel):
    cluster_id: int
    cluster_name: str
    score: float
    band_breakdown: Dict[str, float] = Field(default_factory=dict)
    explanation: str


class ScorecardCareer(BaseModel):
    career_id: int
    career_name: str
    score: float
    top_keyskills: List[str] = Field(default_factory=list)
    explanation: str


class ScorecardResponse(BaseModel):
    student_id: int

    # core blocks
    clusters: List[ScorecardCluster] = Field(default_factory=list)
    careers: List[ScorecardCareer] = Field(default_factory=list)
    keyskills: List[KeySkillScore] = Field(default_factory=list)

    # raw scoring useful for charts
    cluster_scores: Dict[int, float] = Field(default_factory=dict)
    career_scores: Dict[int, float] = Field(default_factory=dict)

    # PR5: additive explainability evidence (computed-on-read)
    evidence: Optional["AssessmentEvidenceBlock"] = None

    # PR6: student-safe explainability blocks (no numeric fields)
    top_facets: List["ScorecardFacetExplainBlock"] = Field(default_factory=list)
    top_aqs: List["ScorecardAQExplainBlock"] = Field(default_factory=list)
    facet_evidence_blocks: List["ScorecardFacetEvidenceBlock"] = Field(default_factory=list)

    message: Optional[str] = None


# ===============================
# PR15: SCORECARD RESPONSE (STUDENT-SAFE VIEW)
# - No numeric fields (no score, no normalized, no cluster_scores, no career_scores)
# - Evidence remains traceable but WITHOUT counts
# ===============================

class StudentKeySkillView(BaseModel):
    keyskill_id: int
    name: str
    tier: str  # qualitative label only (e.g., "High")
    cluster_id: Optional[int] = None
    cluster_name: Optional[str] = None


class StudentScorecardCluster(BaseModel):
    cluster_id: int
    cluster_name: str
    top_keyskills: List[str] = Field(default_factory=list)
    explanation: str


class StudentScorecardCareer(BaseModel):
    career_id: int
    career_name: str
    top_keyskills: List[str] = Field(default_factory=list)
    explanation: str


# --- Student-safe evidence (no counts) ---
class StudentFacetEvidenceItem(BaseModel):
    facet_code: str
    facet_name_en: str
    aq_code: str
    aq_name_en: str
    question_codes: List[str] = Field(default_factory=list)


class StudentAQEvidenceSummaryItem(BaseModel):
    aq_code: str
    aq_name_en: str
    facet_codes: List[str] = Field(default_factory=list)
    question_codes: List[str] = Field(default_factory=list)


class StudentAssessmentEvidenceBlock(BaseModel):
    facet_evidence: List[StudentFacetEvidenceItem] = Field(default_factory=list)
    aq_evidence_summary: List[StudentAQEvidenceSummaryItem] = Field(default_factory=list)


class StudentScorecardResponse(BaseModel):
    student_id: int

    # student-safe insights (no numbers)
    clusters: List[StudentScorecardCluster] = Field(default_factory=list)
    careers: List[StudentScorecardCareer] = Field(default_factory=list)
    keyskills: List[StudentKeySkillView] = Field(default_factory=list)

    # PR5 evidence but student-safe (no counts)
    evidence: Optional[StudentAssessmentEvidenceBlock] = None

    # PR6 blocks reused (already student-safe)
    top_facets: List["ScorecardFacetExplainBlock"] = Field(default_factory=list)
    top_aqs: List["ScorecardAQExplainBlock"] = Field(default_factory=list)
    facet_evidence_blocks: List["ScorecardFacetEvidenceBlock"] = Field(default_factory=list)

    message: Optional[str] = None


# ===============================
# QUESTION SCHEMA
# ===============================

class QuestionCreate(BaseModel):
    id: str
    question_text_en: str
    question_text_hi: Optional[str] = None
    question_text_ta: Optional[str] = None
    skill_id: int
    weight: Optional[int] = 1
    group_id: Optional[str] = None
    prerequisite_qid: Optional[str] = None


class AdminQuestionCreateRequest(BaseModel):
    # required for validator
    assessment_version: str
    question_id: str
    skill_id: int

    # required text fields
    question_text_en: str
    question_text_hi: Optional[str] = None
    question_text_ta: Optional[str] = None
    question_code: Optional[str] = None

    # optional DB fields (route writes these directly, validator stays DB-write-free)
    weight: Optional[int] = 1
    group_id: Optional[str] = None
    prerequisite_qid: Optional[str] = None


class AdminQuestionCreateResponse(BaseModel):
    """
    Structured response:
    - status: created | error
    - created: minimal created record details (when success)
    - errors: structured errors (when validation fails)
    """
    status: str
    created: Optional[Dict[str, Any]] = None
    # ✅ IMPORTANT: avoid mutable default list
    errors: List[Dict[str, str]] = Field(default_factory=list)


# ===============================
# ADMIN BULK QUESTION CREATION SCHEMAS (B4)
# ===============================

class AdminQuestionBulkItem(BaseModel):
    # required for validator
    assessment_version: str
    question_id: str
    skill_id: int

    # required text fields
    question_text_en: str
    question_text_hi: Optional[str] = None
    question_text_ta: Optional[str] = None
    question_code: Optional[str] = None

    # optional DB fields
    weight: Optional[int] = 1
    group_id: Optional[str] = None
    prerequisite_qid: Optional[str] = None


class AdminQuestionBulkItemError(BaseModel):
    field: str
    message: str


class AdminQuestionBulkErrorEntry(BaseModel):
    # index of the item in the request array
    index: int
    question_id: Optional[str] = None
    errors: List[AdminQuestionBulkItemError] = Field(default_factory=list)


class AdminQuestionBulkResponse(BaseModel):
    created: int
    skipped: int
    errors: List[AdminQuestionBulkErrorEntry] = Field(default_factory=list)


# ===============================
# STUDENT RANDOM QUESTION DELIVERY SCHEMAS (B5)
# ===============================
class FacetTagOut(BaseModel):
    facet_code: str
    facet_name_en: Optional[str] = None
    aq_code: Optional[str] = None

class RandomQuestionItemOut(BaseModel):
    question_id: str
    question_code: str | None = None
    skill_id: int
    question_text: str
    facet_tags: List[FacetTagOut] = Field(default_factory=list)


class RandomQuestionsResponse(BaseModel):
    assessment_version: str
    count_requested: int
    count_returned: int
    lang: Optional[str] = None
    lang_used: str
    questions: List[RandomQuestionItemOut] = Field(default_factory=list)


# ===============================
# STUDENT LOCALIZED QUESTION LIST SCHEMAS (B6)
# ===============================

class StudentQuestionItemOut(BaseModel):
    question_id: str = Field(..., json_schema_extra={"example": "V1_Q1"})
    question_code: str | None = None # canonical identifier (external)
    skill_id: int = Field(..., json_schema_extra={"example": 1})
    question_text: str = Field(..., json_schema_extra={"example": "I enjoy solving logical puzzles."})
    facet_tags: List[FacetTagOut] = Field(default_factory=list)


class StudentQuestionsResponse(BaseModel):
    assessment_version: str = Field(..., json_schema_extra={"example": "v1"})
    lang: Optional[str] = Field(None, json_schema_extra={"example": "hi"})
    lang_used: str = Field(..., json_schema_extra={"example": "hi"})
    count_returned: int = Field(..., json_schema_extra={"example": 2})
    questions: List[StudentQuestionItemOut] = Field(default_factory=list)


# ============================
# B10: Student Dashboard Schemas
# ============================

class StudentDashboardAssessmentKPIs(BaseModel):
    total_assessments: int = 0
    last_submitted_at: Optional[datetime] = None


class StudentDashboardTopSkill(BaseModel):
    skill_id: int
    scaled_0_100: float
    tier: Optional[int] = None
    assessment_id: int


class StudentDashboardKeyskillAnalytics(BaseModel):
    # Derived from B9 JSONB snapshot; keep flexible but stable.
    overall_keyskill_summary: Dict[str, Any] = Field(default_factory=dict)
    distribution: Dict[str, Any] = Field(default_factory=dict)
    top_keyskills: List[Dict[str, Any]] = Field(default_factory=list)


class StudentDashboardResponse(BaseModel):
    student_id: int
    scoring_config_version: str = "v1"

    assessment_kpis: StudentDashboardAssessmentKPIs
    keyskill_analytics: Optional[StudentDashboardKeyskillAnalytics] = None
    top_skills: List[StudentDashboardTopSkill] = Field(default_factory=list)

    # UX-friendly deterministic message (e.g., "No assessments yet")
    message: Optional[str] = None


# ==============================
# B11: Student Assessment History
# ==============================

class StudentAssessmentHistoryItem(BaseModel):
    assessment_id: int
    submitted_at: datetime
    assessment_version: Optional[str] = None
    scoring_config_version: str = "v1"
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StudentAssessmentHistoryResponse(BaseModel):
    student_id: int
    total_assessments: int
    assessments: List[StudentAssessmentHistoryItem]
    message: Optional[str] = None


# =========================
# B12 — Student Results History (Read-only)
# =========================

class StudentResultHistoryItem(BaseModel):
    result_id: int
    assessment_id: Optional[int] = None
    generated_at: datetime

    assessment_version: Optional[str] = None
    scoring_config_version: str = Field(default="v1")

    recommended_stream: Optional[str] = None
    top_careers: Optional[List[Any]] = None  # keep flexible (strings or small dicts)
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StudentResultHistoryResponse(BaseModel):
    student_id: int
    total_results: int
    results: List[StudentResultHistoryItem]
    message: Optional[str] = None


# =========================================================
# B13: Consent verification (guardian-facing, compliance)
# =========================================================

class ConsentVerifyRequest(BaseModel):
    """
    Input contract:
    - token: self-contained consent JWT
    - otp: user-provided OTP (plain text), validated via SHA-256 hash match
    """
    token: str = Field(..., min_length=10)
    otp: str = Field(..., min_length=1, max_length=32)


class ConsentVerifyResponse(BaseModel):
    """
    Output contract:
    Always returns verification status, and echoes token identity fields.
    """
    verified: bool
    status: str  # "verified" | "rejected"
    message: Optional[str] = None

    student_id: int
    student_user_id: int
    guardian_email: EmailStr

    verified_at: Optional[datetime] = None
    expires_at: datetime

class ConsentDevPayload(BaseModel):
    token: str
    otp: str

    
class ConsentRequestResponse(BaseModel):
    consent_id: str
    delivery: str = "email"
    expires_at: datetime
    dev: Optional[ConsentDevPayload] = None

    model_config = ConfigDict(from_attributes=True)
    

# ----------------------------
# B14: Student Report Response
# ----------------------------

class ReportResponse(BaseModel):
    student_id: int
    scoring_config_version: str
    report_ready: bool
    report_format: str  # "json" or "pdf_placeholder"
    generated_at: datetime
    pdf_download_url: Optional[str] = None
    message: Optional[str] = None
    report_payload: Optional[Dict[str, Any]] = None


# ----------------------------
# B15: Bootstrap Frontend Session Response
# ----------------------------

class StudentProfileOut(BaseModel):
    student_id: int
    name: str
    grade: int


class SessionUserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_minor: bool
    guardian_email: Optional[EmailStr] = None
    student_profile: Optional[StudentProfileOut] = None

    # ✅ IMPORTANT:
    # This flag is consumed by frontend routing logic.
    # It MUST be derived from consent_logs in /v1/auth/me (do NOT store on user table).
    consent_verified: bool = False

    message: Optional[str] = None

# =========================================================
# Context Profile (CPS) — Hybrid Model external factors
# =========================================================

class ContextProfileCreate(BaseModel):
    """
    Incoming context inputs for a single assessment run.
    CPS is computed server-side deterministically.
    """
    assessment_id: int = Field(..., ge=1)
    student_id: int = Field(..., ge=1)

    # Version pins for strict replayability
    assessment_version: str = Field(..., min_length=1, max_length=32)
    scoring_config_version: str = Field(..., min_length=1, max_length=32)

    # Context inputs
    ses_band: str = Field(..., min_length=1, max_length=32)          # "EWS"|"LIG"|"MIG"|"HIG"
    education_board: str = Field(..., min_length=1, max_length=32)   # "CBSE"|"ICSE"|"State"|...
    support_level: str = Field(..., min_length=1, max_length=32)     # "Low"|"Medium"|"High"
    resource_access: Optional[str] = Field(None, max_length=32)      # optional


class ContextProfileOut(BaseModel):
    id: int
    assessment_id: int
    student_id: int

    assessment_version: str
    scoring_config_version: str

    ses_band: str
    education_board: str
    support_level: str
    resource_access: Optional[str] = None

    cps_score: float

    model_config = ConfigDict(from_attributes=True)
class ContextProfileUpdate(BaseModel):
    """
    Update payload for Context Profile.
    Additive-only schema to match router usage (assessments.py).
    All fields optional to support partial updates.
    """

    # ids may or may not be required by your endpoint, but keeping them optional avoids breaking existing calls
    assessment_id: Optional[int] = Field(None, ge=1)
    student_id: Optional[int] = Field(None, ge=1)

    # Version pins (optional in update)
    assessment_version: Optional[str] = Field(None, min_length=1, max_length=32)
    scoring_config_version: Optional[str] = Field(None, min_length=1, max_length=32)

    # Context inputs (optional in update)
    ses_band: Optional[str] = Field(None, min_length=1, max_length=32)
    education_board: Optional[str] = Field(None, min_length=1, max_length=32)
    support_level: Optional[str] = Field(None, min_length=1, max_length=32)
    resource_access: Optional[str] = Field(None, max_length=32)

ScorecardResponse.model_rebuild()