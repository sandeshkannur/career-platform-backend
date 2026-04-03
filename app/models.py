# backend/app/models.py
"""
SQLAlchemy ORM models for the FastAPI + PostgreSQL assessment platform.


"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Date,
    Boolean,
    Table,
    DateTime,
    Float,
    UniqueConstraint,
    Index,
    Numeric,
    Text,
    SmallInteger,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB  # ✅ for JSONB columns
from sqlalchemy import JSON

from .database import Base

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


# =========================================================
# Core identity & profiles
# =========================================================

class User(Base):
    """
    User model – supports minors and roles (auth identity).
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    dob = Column(Date, nullable=False)
    is_minor = Column(Boolean, nullable=False, default=False)
    tier = Column(String, nullable=False, default="free")
    guardian_email = Column(String, nullable=True)
    role = Column(String, nullable=False, default="student")


class Student(Base):
    """
    Student – student profile (used by assessment + analytics).

    ✅ Architecture Fix (already implemented in your locked foundation):
    - Link student profile to a user account.
    - users.id (auth) -> students.id (profile) mapping for analytics tables.
    - Kept nullable for backward compatibility during migration/backfill.
    """
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    grade = Column(Integer, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, unique=True, index=True)

    # 1:1 relationship to User (optional until backfilled)
    user = relationship("User", backref="student_profile", uselist=False)
    
# =========================================================
# Context Profile (CPS) — Hybrid Model external factors
# =========================================================

class ContextProfile(Base):
    """
    ContextProfile — captures external/context factors for a specific assessment run.

    Stored per-assessment for strict replayability:
    old results can be recomputed using the exact context factors at run-time.
    """
    __tablename__ = "context_profile"

    id = Column(Integer, primary_key=True, index=True)

    # Pin to the immutable assessment run (1:1)
    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Student reference
    student_id = Column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Version pins (for strict audit/replay)
    assessment_version = Column(String(32), nullable=False, index=True, default="v1")
    scoring_config_version = Column(String(32), nullable=False, index=True, default="v1")

    # Context inputs
    ses_band = Column(String(32), nullable=False)            # e.g. "EWS", "LIG", "MIG", "HIG"
    education_board = Column(String(32), nullable=False)     # e.g. "CBSE", "ICSE", "State"
    support_level = Column(String(32), nullable=False)       # e.g. "Low", "Medium", "High"
    resource_access = Column(String(32), nullable=True)      # optional for now

    # Computed output (0–100)
    cps_score = Column(Float, nullable=False, default=0.0)

    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_context_profile_student_version", "student_id", "scoring_config_version"),
    )

    # Relationships (additive & safe)
    student = relationship("Student", backref="context_profiles")
    assessment = relationship("Assessment", backref="context_profile")


# =========================================================
# Skill domain
# =========================================================

class Skill(Base):
    """
    Skill – individual skills.
    """
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    display_name = Column(String(200), nullable=True)
    # Sprint1: full canonical Student Skill name (maps short DB name → master sheet name)
    student_skill_name = Column(String(128), nullable=True)

class SkillAlias(Base):
    """
    PR42: Alias → Canonical mapping used during ingestion.

    entity_type:
      - "AQ"    (Associated Quality codes)
      - "FACET" (Facet codes)
      - "SKILL" (Student-skill name aliases, if needed later)

    assessment_version:
      - If set, alias applies only to that version
      - If NULL, alias is global fallback
    """
    __tablename__ = "skill_aliases"

    id = Column(Integer, primary_key=True, index=True)

    entity_type = Column(String(20), nullable=False)
    assessment_version = Column(String(32), nullable=True)

    alias = Column(String(200), nullable=False)
    canonical_code = Column(String(200), nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

class StudentSkillMap(Base):
    """
    Student ↔ Skill (many-to-many)  [LEGACY SKILL MAP]
    """
    __tablename__ = "student_skill_map"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False)

    student = relationship("Student", backref="skill_maps")
    skill = relationship("Skill", backref="student_maps")


# =========================================================
# Careers, clusters, key skills
# =========================================================

class CareerCluster(Base):
    """
    Career Clusters – group careers.
    """
    __tablename__ = "career_clusters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)

    key_skills = relationship("KeySkill", back_populates="cluster")
    careers = relationship("Career", back_populates="cluster")


# Career ↔ KeySkill association (many-to-many) with weight %
career_keyskill_association = Table(
    "career_keyskill_association",
    Base.metadata,
    Column("career_id", Integer, ForeignKey("careers.id"), primary_key=True),
    Column("keyskill_id", Integer, ForeignKey("keyskills.id"), primary_key=True),
    # weight percentage (0–100) coming from your rationale docs
    Column("weight_percentage", Integer, nullable=False, default=0),
)


class Career(Base):
    """
    Career – individual career entries.
    """
    __tablename__ = "careers"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    career_code = Column(String, unique=True, nullable=False)
    cluster_id = Column(Integer, ForeignKey("career_clusters.id"), nullable=True)
    # Sprint1: denormalised cluster label (populated from master sheet CSV upload)
    cluster = Column(String(64), nullable=True)

    cluster = relationship("CareerCluster", back_populates="careers")
    keyskills = relationship(
        "KeySkill",
        secondary=career_keyskill_association,
        back_populates="careers",
    )


class KeySkill(Base):
    """
    KeySkill – specific skills tied to clusters.
    """
    __tablename__ = "keyskills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)  # used in upload_keyskills
    cluster_id = Column(Integer, ForeignKey("career_clusters.id"), nullable=True)

    cluster = relationship("CareerCluster", back_populates="key_skills")
    careers = relationship(
        "Career",
        secondary=career_keyskill_association,
        back_populates="keyskills",
    )


class StudentKeySkillMap(Base):
    """
    Student ↔ KeySkill (many-to-many, with numeric score)

    NOTE:
    - Your locked B8 foundation indicates this table is upserted deterministically
      from student_skill_scores + skill_keyskill_map.
    - This model remains unchanged here.
    """
    __tablename__ = "student_keyskill_map"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    keyskill_id = Column(Integer, ForeignKey("keyskills.id"), nullable=False)

    # numeric score (0–100) representing key skill strength for the student.
    # If NULL, treat as 100 (legacy behavior).
    score = Column(Float, nullable=True)

    student = relationship("Student", backref="keyskill_maps")
    keyskill = relationship("KeySkill", backref="student_maps")


class SkillKeySkillMap(Base):
    """
    Skill ↔ KeySkill (many-to-many mapping for analytics)
    """
    __tablename__ = "skill_keyskill_map"

    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False)
    keyskill_id = Column(Integer, ForeignKey("keyskills.id"), nullable=False)

    # Optional weight (future-proof). Default 1.0 = equal contribution.
    weight = Column(Float, nullable=False, default=1.0)

    __table_args__ = (
        UniqueConstraint("skill_id", "keyskill_id", name="uq_skill_keyskill"),
    )

    skill = relationship("Skill", backref="keyskill_maps")
    keyskill = relationship("KeySkill", backref="skill_maps")

# ---------------------------
# PR21: i18n foundation models
# ---------------------------

class Language(Base):
    __tablename__ = "languages"

    code = Column(String(20), primary_key=True, index=True)
    name = Column(String(80), nullable=False)
    native_name = Column(String(80), nullable=True)
    direction = Column(String(3), nullable=False, default="ltr")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class QuestionTranslation(Base):
    __tablename__ = "question_translations"

    id = Column(Integer, primary_key=True, index=True)
    assessment_version = Column(String(50), nullable=False, index=True)

    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    locale = Column(String(20), ForeignKey("languages.code", ondelete="RESTRICT"), nullable=False, index=True)

    question_text = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FacetTranslation(Base):
    __tablename__ = "facet_translations"

    id = Column(Integer, primary_key=True, index=True)
    facet_id = Column(String(120), ForeignKey("aq_facets.facet_id", ondelete="RESTRICT"), nullable=False, index=True)
    locale = Column(String(20), ForeignKey("languages.code", ondelete="RESTRICT"), nullable=False, index=True)

    facet_name = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExplanationTranslation(Base):
    __tablename__ = "explanation_translations"

    id = Column(Integer, primary_key=True, index=True)
    content_version = Column(String(32), nullable=False, index=True)
    locale = Column(String(20), ForeignKey("languages.code", ondelete="RESTRICT"), nullable=False, index=True)

    explanation_key = Column(String(120), nullable=False, index=True)
    text = Column(Text, nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# =========================================================
# Questions (assessment item bank)
# =========================================================

class Question(Base):
    """
    Question – multilingual + skill mapping + branching.
    """
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_version = Column(String, nullable=False, index=True)

    question_text_en = Column(String, nullable=False)
    question_text_hi = Column(String)
    question_text_ta = Column(String)

    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False)

    weight = Column(Integer, default=1)
    group_id = Column(String)

    prerequisite_qid = Column(Integer, ForeignKey("questions.id"), nullable=True)

    skill = relationship("Skill", backref="questions")
    prerequisite = relationship("Question", remote_side=[id], backref="dependents")
    question_code = Column(String(100), nullable=True)
    chapter_id = Column(SmallInteger, nullable=True)
    pool_id = Column(String(1), nullable=True)
    question_type = Column(String(30), nullable=False, server_default='likert')
    response_options = Column(JSONB, nullable=True)
    renderer_config = Column(JSONB, nullable=True)
    format_version = Column(String(10), nullable=False, server_default='v1')


# =========================================================
# Assessment engine tables
# =========================================================

class AssessmentQuestion(Base):
    """
    AssessmentQuestion — persisted question set for an assessment attempt.

    Used to enforce:
    - 75 questions total (3 per AQ across AQ_01..AQ_25)
    - deterministic replay + auditability
    """
    __tablename__ = "assessment_questions"

    id = Column(Integer, primary_key=True, index=True)

    assessment_id = Column(
        Integer,
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)

    assessment_version = Column(String(32), nullable=False, index=True)
    question_code = Column(String(100), nullable=False)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

class Assessment(Base):
    """
    Assessment – per-user assessment attempt.
    """
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    assessment_version = Column(String(32), nullable=False, default="v1", index=True)
    scoring_config_version = Column(String(32), nullable=False, default="v1", index=True)
    question_pool_version = Column(String(32), nullable=False, default="v1", index=True)

    responses = relationship("AssessmentResponse", back_populates="assessment")
    result = relationship("AssessmentResult", uselist=False, back_populates="assessment")


class AssessmentResponse(Base):
    """
    AssessmentResponse – raw answers captured per question.
    """
    __tablename__ = "assessment_responses"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False, index=True)
    # PR33: stable external identifier (do NOT depend on UI / language)
    question_code = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    # PR33: strict FK-first identifier for joins, scoring, explainability
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)

    answer_value = Column(Integer, nullable=True)

    # NEW: idempotency key for offline replay safety (nullable for backward compatibility)
    idempotency_key = Column(String(80), nullable=True, index=True)

    __table_args__ = (
        # Existing immutability constraint stays
        UniqueConstraint(
            "assessment_id",
            "question_id",
            name="uq_assessment_responses_assessment_question",
        ),
        # NEW: idempotency uniqueness per assessment
        UniqueConstraint(
            "assessment_id",
            "idempotency_key",
            name="uq_assessment_responses_assessment_id_idempotency_key",
        ),
        # Optional but useful for fast lookups
        Index(
            "ix_assessment_responses_assessment_id_idempotency_key",
            "assessment_id",
            "idempotency_key",
        ),
    )

    assessment = relationship("Assessment", back_populates="responses")


class AssessmentResult(Base):
    """
    AssessmentResult – recommendation outputs stored as JSON.
    """
    __tablename__ = "assessment_results"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), unique=True, nullable=False)
    recommended_stream = Column(String, nullable=True)

    # Store careers as JSON (list or dict) to avoid stringifying
    recommended_careers = Column(JSON_TYPE, nullable=True)

    # per-skill tiers/levels produced by scoring/analytics
    # Example: {"Creativity": "Intermediate", "Numerical Reasoning": "Advanced"}
    skill_tiers = Column(JSON_TYPE, nullable=True)
    
    # PR44: Internal-only deterministic contribution trace for QA/audit (never returned to students)
    contrib_trace = Column(JSON_TYPE, nullable=True)

    # =========================================================
    # PR40: Version bundle pinning (auditability)
    # These are pinned at report generation time.
    # - assessment_version: which question set/assessment bundle was used
    # - scoring_config_version: which scoring ruleset was used
    # - content_version: which CMS/explainability content bundle was used
    # =========================================================
    assessment_version = Column(String(32), nullable=True, index=True)
    scoring_config_version = Column(String(32), nullable=True, index=True)
    content_version = Column(String(32), nullable=True, index=True)
    
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    assessment = relationship("Assessment", back_populates="result")


# =========================================================
# B7: Student Skill Scores (scoring outputs)
# =========================================================

class StudentSkillScore(Base):
    """
    StudentSkillScore – computed per-skill scoring output.

    Locked B7 behavior notes:
    - Unique (assessment_id, scoring_config_version, skill_id) ensures idempotency.
    - Stores raw_total, question_count, avg_raw, scaled_0_100.
    - Additive HSI persistence fields (nullable) for replay-safe analytics (Option A).
    """
    __tablename__ = "student_skill_scores"

    id = Column(Integer, primary_key=True, index=True)

    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False, index=True)

    # IMPORTANT: kept exactly as you currently have it (do not change B1–B8 contracts/behavior).
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    scoring_config_version = Column(String, nullable=False, index=True, default="v1")
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False, index=True)

    # v1 "raw" signals (no exact normalization table yet)
    raw_total = Column(Float, nullable=False)  # sum of numeric answers (or weighted)
    question_count = Column(Integer, nullable=False)

    # store a simple derived score for now (can be replaced/refined later)
    avg_raw = Column(Float, nullable=False)  # raw_total / question_count
    scaled_0_100 = Column(Float, nullable=False)  # avg_raw converted to 0..100 (temporary)

    # =========================================================
    # HSI persistence (Option A) - ADDITIVE, nullable, version-safe
    # =========================================================
    hsi_score = Column(Float, nullable=True)
    cps_score_used = Column(Float, nullable=True)
    assessment_version = Column(String(20), nullable=True)

    computed_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
    UniqueConstraint(
        "assessment_id",
        "scoring_config_version",
        "skill_id",
        name="uq_student_skill_scores_assessment_version_skill",
    ),
    )
# =========================================================
# B9: Analytics snapshots (NEW - additive)
# =========================================================

class StudentAnalyticsSummary(Base):
    """
    B9 Analytics snapshot table (idempotent upsert).
    One row per (student_id, scoring_config_version).
    payload_json stores dashboard-ready computed aggregates.

    Table already created by SQL:
      student_analytics_summary
        - unique(student_id, scoring_config_version)
    """
    __tablename__ = "student_analytics_summary"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    scoring_config_version = Column(String, nullable=False, default="v1", index=True)

    payload_json = Column(JSON_TYPE, nullable=False)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "scoring_config_version", name="uq_student_analytics_student_version"),
        Index("ix_student_analytics_student_version", "student_id", "scoring_config_version"),
    )

    # Optional relationship (safe/additive)
    student = relationship("Student", backref="analytics_summaries")

# =========================================================
# B13: Consent verification logs (WRITE-ONLY, auditable)
# =========================================================

class ConsentLog(Base):
    """
    ConsentLog – audit log for parental/guardian consent verification attempts.

    B13 rules:
    - WRITE ONLY: used to record every verification attempt (verified or rejected).
    - Token validation must NOT read DB (no reads required here).
    - Pure audit trail: store enough info to investigate disputes later.
    """
    __tablename__ = "consent_logs"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(Integer, nullable=False, index=True)
    student_user_id = Column(Integer, nullable=False, index=True)

    guardian_email = Column(String(320), nullable=False, index=True)

    # optional JWT jti (unique token id)
    token_jti = Column(String(128), nullable=True, index=True)

    # verified / rejected
    status = Column(String(32), nullable=False, index=True)

    # reason for rejection: invalid_token / expired_token / invalid_otp / guardian_mismatch
    reason = Column(String(64), nullable=True, index=True)

    # optional additional details (safe for debugging)
    message = Column(Text, nullable=True)

    verified_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    ip = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

# =========================================================
# Associated Quality (AQ) and AQFacet
# =========================================================

class AssociatedQuality(Base):
    __tablename__ = "associated_qualities"

    aq_id = Column(String, primary_key=True, index=True)   # e.g., "AQ_01"
    aq_name = Column(String, nullable=False)               # e.g., "Curiosity Drive"

    facets = relationship("AQFacet", back_populates="aq", cascade="all, delete-orphan")


class AQFacet(Base):
    __tablename__ = "aq_facets"

    facet_id = Column(String, primary_key=True, index=True)  # e.g., "AQ01_F1"
    aq_id = Column(String, ForeignKey("associated_qualities.aq_id", ondelete="RESTRICT"), nullable=False, index=True)
    facet_name = Column(String, nullable=False)

    aq = relationship("AssociatedQuality", back_populates="facets")


# Helpful explicit index (some DBs already index FK col; we make it explicit)
Index("idx_aq_facets_aq_id", AQFacet.aq_id)

# =========================================================
# PR2: Question ↔ AQFacet tagging
# =========================================================

class QuestionFacetTag(Base):
    """
    QuestionFacetTag — tags a question to one or more AQ facets.
    Backend-authoritative mapping used for explainability and analytics.
    """
    __tablename__ = "question_facet_tags"

    id = Column(Integer, primary_key=True, index=True)

    # FK -> questions.id (INTEGER)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)

    # FK -> aq_facets.facet_id (STRING)
    facet_id = Column(String, ForeignKey("aq_facets.facet_id", ondelete="RESTRICT"), nullable=False, index=True)

    __table_args__ = (
    UniqueConstraint(
        "question_id",
        "facet_id",
        name="uq_question_facet_tags_question_facet",
    ),
    )   

    # Optional relationships (safe/additive)
    question = relationship("Question", backref="facet_tags")
    facet = relationship("AQFacet", backref="question_tags")

# =========================================================
# PR45: Question → StudentSkill Weights (QSSW)
# =========================================================

class QuestionStudentSkillWeight(Base):
    """
    PR45: Deterministic mapping of Question -> Student Skill with numeric weights.

    IMPORTANT:
    - This model is for ADMIN ingestion + future scoring.
    - Adding this model alone does NOT change scoring/explainability.
    """
    __tablename__ = "question_student_skill_weights"

    id = Column(Integer, primary_key=True, index=True)

    question_id = Column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False, index=True)

    weight = Column(Numeric(6, 4), nullable=False)

    # Optional metadata (already present in your DB table)
    source = Column(String(200), nullable=True)
    facet_id = Column(String(50), nullable=True)
    aq_id = Column(String(50), nullable=True)

    __table_args__ = (
        UniqueConstraint("question_id", "skill_id", name="question_student_skill_weights_question_id_skill_id_key"),
    )

    # Optional relationships (safe/additive)
    question = relationship("Question", backref="student_skill_weights")
    skill = relationship("Skill", backref="question_weights")

# =========================================================
# PR16: CMS-backed explainability content (versioned + locale-aware)
# =========================================================

class ExplainabilityContent(Base):
    __tablename__ = "explainability_content"

    id = Column(Integer, primary_key=True, index=True)

    # Content version pin (e.g., "v1")
    version = Column(String(32), nullable=False, index=True)

    # Locale code (e.g., "en", "kn-IN")
    locale = Column(String(20), nullable=False, index=True)

    # Stable lookup key used by frontend/backend projections
    explanation_key = Column(String(120), nullable=False, index=True)

    # Student-safe copy only (no analytics)
    text = Column(Text, nullable=False)

    # Active flag so we can deactivate copy without deleting
    is_active = Column(Boolean, nullable=False, default=True)

    # Audit-friendly timestamp
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("version", "locale", "explanation_key", name="uq_explainability_content_v_l_k"),
    )


# =========================================================
# ADM-B01: SME (Subject Matter Expert) Profile
# Part of the A01 SME Validation & Expert Management section.
#
# Weighting approach: Approach B — credentials × calibration composite.
#
#   credentials_score = (years_experience × 0.4)
#                     + (seniority_score   × 0.3)
#                     + (education_score   × 0.2)
#                     + (sector_relevance  × 0.1)
#
#   calibration_score = 1 - mean_absolute_deviation_from_group_median
#                     (computed by aggregation service, stored here for audit)
#
#   effective_weight  = credentials_score × calibration_score
#                     (never stored — always recomputed by ADM-B03 service)
#
# Deactivation rule: NEVER DELETE rows — set status = 'inactive'.
# This preserves the full audit trail of who validated which careers.
# =========================================================

class SMEProfile(Base):
    """
    Subject Matter Expert profile — one row per SME.

    Stores identity, career assignments, experience-based credential
    inputs, and the calibration score computed after each submission
    round by the weighted aggregation service (ADM-B03).

    The effective_weight used in final career-AQ aggregation is:
        effective_weight = credentials_score * calibration_score
    This is never persisted here — it is computed fresh each time
    so it always reflects the most recent calibration round.
    """
    __tablename__ = "sme_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # ── Identity ──────────────────────────────────────────────────
    full_name = Column(String(200), nullable=False)
    email     = Column(String(200), unique=True, nullable=False, index=True)

    # ── Career assignments ────────────────────────────────────────
    # Comma-separated career IDs for now.
    # Will be normalised to sme_career_assignments join table in ADM-B46.
    # Hard cap: max 3 careers per SME to protect IP across career profiles.
    career_assignments = Column(Text, nullable=True)

    # ── Credential inputs (used to compute credentials_score) ─────
    # All scores are normalised 0.0 – 1.0 before storage.
    # Raw values (e.g. actual years) are in context_notes if needed.
    years_experience  = Column(Integer, nullable=True)   # raw years (e.g. 12)
    seniority_score   = Column(Float,   nullable=True)   # 0.0 – 1.0
    education_score   = Column(Float,   nullable=True)   # 0.0 – 1.0
    sector_relevance  = Column(Float,   nullable=True)   # 0.0 – 1.0

    # ── Computed credential score ─────────────────────────────────
    # credentials_score = (years×0.4) + (seniority×0.3)
    #                   + (education×0.2) + (sector×0.1)
    # Recomputed and stored whenever credential inputs change.
    credentials_score = Column(Float, nullable=True)

    # ── Calibration score (set by aggregation service, ADM-B03) ───
    # calibration_score = 1 - mean_absolute_deviation_from_group_median
    # Null until the SME has at least one completed submission round.
    # Range: 0.0 (complete outlier) to 1.0 (perfect consensus alignment)
    calibration_score = Column(Float, nullable=True)

    # ── Submission tracking ───────────────────────────────────────
    # Total career forms completed by this SME across all rounds.
    # Used to give higher implicit trust to experienced SME respondents.
    submission_count = Column(Integer, nullable=False, default=0)

    # ── Context fields ────────────────────────────────────────────
    sector    = Column(String(200), nullable=True)  # e.g. "Healthcare", "IT"
    education = Column(String(200), nullable=True)  # e.g. "PhD Psychology"

    # ── Lifecycle ─────────────────────────────────────────────────
    # status: 'active' | 'inactive'
    # Use 'inactive' for deactivation — NEVER DELETE rows.
    status = Column(String(20), nullable=False, default="active", index=True)

    # ── Audit timestamps ──────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_sme_profiles_email"),
        Index("ix_sme_profiles_status", "status"),
    )


# =========================================================
# ADM-B02: SME Submission Pipeline
# Part of the A01 SME Validation & Expert Management section.
#
# Flow:
#   1. Admin creates a token → sme_submission_tokens (one per SME+career+round)
#   2. Token link sent to SME → SME opens /sme/form/{token}
#   3. SME accepts confidentiality disclaimer → disclaimer stored with audit trail
#   4. SME submits ratings → sme_aq_ratings + sme_keyskill_ratings
#   5. SME may suggest missing key skills → sme_keyskill_suggestions (review queue)
#
# Rating scale: SME enters 0–10 integer. Backend stores as 0.0–1.0 (÷10).
# This matches the scoring engine's internal weight format exactly.
#
# Token security: token is a UUID4. Knowledge of the token = authorisation.
# No login required for SME-facing endpoints.
#
# Disclaimer: v1.0 stored as DISCLAIMER_V1 constant in this module.
# Every submission records which version was accepted + timestamp + IP.
# When disclaimer text changes, bump the version string.
# =========================================================

# ── Disclaimer text registry ──────────────────────────────────────────────
# Versioned disclaimer text. Store the active version key on each submission.
# When text changes: add a new key (e.g. "v1.1"), never edit existing keys.
DISCLAIMER_VERSIONS = {
    "v1.0": """CONFIDENTIALITY & INTELLECTUAL PROPERTY ACKNOWLEDGEMENT

By submitting this form, I acknowledge and agree to the following:

1. Proprietary Information
   The career profiles, Associated Quality (AQ) frameworks, and key skill
   mappings presented in this form are the exclusive intellectual property
   of MYC Edtech LLP ("MapYourCareer") and are strictly confidential.

2. Permitted Use
   I am providing my expert ratings solely for the purpose of validating
   career assessment weightings on the MapYourCareer.in platform. My
   contributions will be used to improve career guidance outcomes for
   students across India.

3. Non-Disclosure
   I agree not to share, reproduce, copy, transmit, or disclose any
   information contained in this form — including career names, AQ
   definitions, key skill mappings, or weight structures — to any third
   party, in any form, without prior written consent from MYC Edtech LLP.

4. No Competing Use
   I confirm that my ratings represent my honest professional opinion and
   will not be used to benefit any competing platform, organisation, or
   commercial interest.

5. Data Consent
   I consent to MYC Edtech LLP storing my name, email address,
   professional credentials, and submitted ratings for the purpose of
   career assessment validation. This data will be handled in accordance
   with applicable Indian data protection laws including the Digital
   Personal Data Protection Act, 2023.

6. Acceptance
   I confirm that I have read, understood, and agree to the terms above.
   This acceptance is recorded with a timestamp and will be retained
   by MYC Edtech LLP as part of the audit trail for this validation round.

— MapYourCareer.in | MYC Edtech LLP""",
}

# The currently active disclaimer version — update this when text changes
ACTIVE_DISCLAIMER_VERSION = "v1.0"


class SMESubmissionToken(Base):
    """
    One token per SME+career+round combination.

    Generated by admin via POST /admin/sme/{sme_id}/tokens.
    Sent to SME as a unique URL: /sme/form/{token}
    Token knowledge = authorisation — no login required.

    Status lifecycle: pending → submitted (or) pending → expired
    Expired tokens reject submissions. Already-submitted tokens
    reject duplicate submissions.

    Disclaimer audit trail:
    - disclaimer_version: which version of the disclaimer was shown
    - disclaimer_accepted: True only after SME ticked the checkbox
    - disclaimer_accepted_at: timestamp with timezone (DPDP Act compliance)
    - disclaimer_ip_address: IP address at time of acceptance (audit evidence)
    """
    __tablename__ = "sme_submission_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    sme_id     = Column(Integer, ForeignKey("sme_profiles.id"), nullable=False, index=True)
    career_id  = Column(Integer, ForeignKey("careers.id"), nullable=False, index=True)

    # UUID4 token — knowledge of this value = authorisation to submit
    token      = Column(String(64), unique=True, nullable=False, index=True)

    # Which validation round this token belongs to (1, 2, 3…)
    round_number = Column(Integer, nullable=False, default=1)

    # status: 'pending' | 'submitted' | 'expired'
    status     = Column(String(20), nullable=False, default="pending", index=True)

    # Token expiry — admin sets this; default 14 days from creation
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # ── Disclaimer audit trail (DPDP Act + global best practice) ─────────
    # disclaimer_version: matches a key in DISCLAIMER_VERSIONS dict
    disclaimer_version     = Column(String(10),  nullable=True)
    disclaimer_accepted    = Column(Boolean,     nullable=False, default=False)
    disclaimer_accepted_at = Column(DateTime(timezone=True), nullable=True)
    # IP stored as string to support both IPv4 and IPv6
    disclaimer_ip_address  = Column(String(45),  nullable=True)

    # Audit timestamps
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    sme              = relationship("SMEProfile")
    career           = relationship("Career")
    aq_ratings       = relationship("SMEAQRating",           back_populates="token", cascade="all, delete-orphan")
    keyskill_ratings = relationship("SMEKeySkillRating",     back_populates="token", cascade="all, delete-orphan")
    suggestions      = relationship("SMEKeySkillSuggestion", back_populates="token", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("sme_id", "career_id", "round_number", name="uq_sme_token_sme_career_round"),
        Index("ix_sme_submission_tokens_status", "status"),
    )


class SMEAQRating(Base):
    """
    One row per AQ rated by an SME for a specific career.

    25 rows created per submission (one per AQ_01 through AQ_25).
    weight_rating stored as 0.0–1.0 (SME input of 0–10 divided by 10).
    confidence stored as 0.0–1.0 — how confident the SME is in their rating.
    """
    __tablename__ = "sme_aq_ratings"

    id        = Column(Integer, primary_key=True, index=True)
    token_id  = Column(Integer, ForeignKey("sme_submission_tokens.id"), nullable=False, index=True)
    sme_id    = Column(Integer, ForeignKey("sme_profiles.id"), nullable=False, index=True)
    career_id = Column(Integer, ForeignKey("careers.id"), nullable=False, index=True)

    # AQ identifier — matches associated_qualities.aq_id (e.g. "AQ_01")
    aq_code       = Column(String(20), nullable=False)

    # SME entered 0–10; stored as 0.0–1.0 (÷10)
    weight_rating = Column(Float, nullable=False)

    # Optional confidence score (0.0–1.0)
    confidence    = Column(Float, nullable=True)

    # Optional free-text justification from SME
    notes         = Column(Text, nullable=True)

    submitted_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    token = relationship("SMESubmissionToken", back_populates="aq_ratings")

    __table_args__ = (
        UniqueConstraint("token_id", "aq_code", name="uq_sme_aq_rating_token_aq"),
        Index("ix_sme_aq_ratings_career_aq", "career_id", "aq_code"),
    )


class SMEKeySkillRating(Base):
    """
    One row per pre-mapped key skill rated by an SME for a specific career.

    Only key skills already mapped to the career in career_keyskill_association
    appear here. weight_rating stored as 0.0–1.0 (SME input ÷ 10).
    """
    __tablename__ = "sme_keyskill_ratings"

    id           = Column(Integer, primary_key=True, index=True)
    token_id     = Column(Integer, ForeignKey("sme_submission_tokens.id"), nullable=False, index=True)
    sme_id       = Column(Integer, ForeignKey("sme_profiles.id"), nullable=False, index=True)
    career_id    = Column(Integer, ForeignKey("careers.id"), nullable=False, index=True)
    keyskill_id  = Column(Integer, ForeignKey("keyskills.id"), nullable=False, index=True)

    # SME entered 0–10; stored as 0.0–1.0 (÷10)
    weight_rating = Column(Float, nullable=False)

    # Optional confidence score (0.0–1.0)
    confidence    = Column(Float, nullable=True)

    # Optional free-text justification from SME
    notes         = Column(Text, nullable=True)

    submitted_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    token    = relationship("SMESubmissionToken", back_populates="keyskill_ratings")
    keyskill = relationship("KeySkill")

    __table_args__ = (
        UniqueConstraint("token_id", "keyskill_id", name="uq_sme_keyskill_rating_token_ks"),
        Index("ix_sme_keyskill_ratings_career_ks", "career_id", "keyskill_id"),
    )


class SMEKeySkillSuggestion(Base):
    """
    Free-text key skill suggestions from SMEs during form submission.

    SMEs can search the existing keyskills table and select a match,
    OR type a new key skill name not yet in the DB.

    Status lifecycle: pending → approved | rejected
    Admin reviews these in Key Skill Library Manager (ADM-B11).
    These rows NEVER auto-modify the keyskills table.
    """
    __tablename__ = "sme_keyskill_suggestions"

    id        = Column(Integer, primary_key=True, index=True)
    token_id  = Column(Integer, ForeignKey("sme_submission_tokens.id"), nullable=False, index=True)
    sme_id    = Column(Integer, ForeignKey("sme_profiles.id"), nullable=False, index=True)
    career_id = Column(Integer, ForeignKey("careers.id"), nullable=False, index=True)

    # If SME selected an existing key skill from search
    existing_keyskill_id  = Column(Integer, ForeignKey("keyskills.id"), nullable=True)

    # If SME typed a new key skill not in DB
    suggested_name        = Column(String(200), nullable=True)
    suggested_description = Column(Text,        nullable=True)

    # How important (0–10 → stored 0.0–1.0)
    importance_rating = Column(Float, nullable=True)

    # Justification from SME
    rationale = Column(Text, nullable=True)

    # Review status: 'pending' | 'approved' | 'rejected'
    review_status = Column(String(20), nullable=False, default="pending", index=True)
    reviewed_by   = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at   = Column(DateTime(timezone=True), nullable=True)

    submitted_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    token             = relationship("SMESubmissionToken", back_populates="suggestions")
    existing_keyskill = relationship("KeySkill")
    reviewer          = relationship("User")

    __table_args__ = (
        Index("ix_sme_keyskill_suggestions_review_status", "review_status"),
    )


# =========================================================
# ADM-B03: Career AQ Weights — Aggregation Engine Output
# Part of the A01 SME Validation & Expert Management section.
#
# This table stores the FINAL computed AQ weights per career+round,
# produced by the weighted aggregation engine (sme_aggregation service).
#
# Algorithm:
#   1. Collect all submitted SME ratings for career+round
#   2. Compute group median per AQ
#   3. Per SME: calibration_score = 1 - mean(|rating - median|) across all AQs
#   4. Per SME: effective_weight = credentials_score × calibration_score
#   5. Per AQ:  final_weight = Σ(rating_i × eff_weight_i) / Σ(eff_weight_i)
#
# This table is the source of truth for career-AQ weight promotion to production.
# Rows are never deleted — each round creates new rows (round_number differentiates).
# =========================================================

class CareerAQWeight(Base):
    """
    Final aggregated AQ weight for a career, computed by ADM-B03 engine.

    One row per career+aq_code+round_number combination.
    Produced by POST /admin/sme/aggregate — never written manually.

    final_weight: the calibration-weighted average of all SME ratings.
    sme_count: how many SMEs contributed to this weight.
    median_rating: group median before weighting (useful for audit).
    std_deviation: spread of SME ratings (high = disagreement between SMEs).
    is_promoted: True once admin promotes this weight to production scoring.
    """
    __tablename__ = "career_aq_weights"

    id           = Column(Integer, primary_key=True, index=True)
    career_id    = Column(Integer, ForeignKey("careers.id"), nullable=False, index=True)
    aq_code      = Column(String(20), nullable=False)
    round_number = Column(Integer,  nullable=False, default=1)

    # ── Aggregation outputs ───────────────────────────────────────────────
    # Calibration-weighted average of all SME ratings for this AQ+career
    final_weight   = Column(Float, nullable=False)

    # Raw statistics for audit and transparency
    median_rating  = Column(Float, nullable=True)   # group median before weighting
    std_deviation  = Column(Float, nullable=True)   # spread of SME ratings
    sme_count      = Column(Integer, nullable=False, default=0)  # contributing SMEs

    # ── Promotion lifecycle ───────────────────────────────────────────────
    # is_promoted: False until admin explicitly promotes via ADM-B16
    # Once promoted, this weight flows into the student scoring engine
    is_promoted    = Column(Boolean, nullable=False, default=False)
    promoted_at    = Column(DateTime(timezone=True), nullable=True)
    promoted_by    = Column(Integer, ForeignKey("users.id"), nullable=True)

    # ── Audit timestamps ──────────────────────────────────────────────────
    computed_at    = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    career   = relationship("Career")
    promoter = relationship("User")

    __table_args__ = (
        # One weight per career+AQ+round — rerunning aggregation overwrites
        UniqueConstraint("career_id", "aq_code", "round_number",
                         name="uq_career_aq_weight_career_aq_round"),
        Index("ix_career_aq_weights_career_id",    "career_id"),
        Index("ix_career_aq_weights_is_promoted",  "is_promoted"),
    )


# =========================================================
# Sprint1: Career → Student Skill weights (new scoring layer)
# =========================================================

class CareerStudentSkill(Base):
    """
    Career ↔ Student Skill weight mapping (Sprint1 scoring rebuild).

    Replaces the broken career_keyskill_association chain for scoring.
    One row per (career_id, student_skill) pair.
    weight is a percentage (0–100); all weights for a career should sum to 100.

    Populated via POST /v1/admin/upload-career-student-skill-weights
    """
    __tablename__ = "career_student_skill"

    career_id     = Column(Integer, ForeignKey("careers.id"), primary_key=True, nullable=False)
    student_skill = Column(String(128), primary_key=True, nullable=False)
    weight        = Column(Numeric(6, 2), nullable=False, default=0)

    career = relationship("Career", backref="student_skill_weights")

    __table_args__ = (
        Index("ix_career_student_skill_career", "career_id"),
        Index("ix_career_student_skill_skill",  "student_skill"),
    )


class AQStudentSkillWeight(Base):
    """
    AQ → Student Skill weight mapping (Sprint1 scoring rebuild).

    Maps each AQ code to student skill names with fractional weights.
    Populated via POST /v1/admin/upload-aq-student-skill-weights
    """
    __tablename__ = "aq_student_skill_weight"

    aq_code       = Column(String(8),   primary_key=True, nullable=False)
    student_skill = Column(String(128), primary_key=True, nullable=False)
    weight        = Column(Numeric(8, 6), nullable=False)

    __table_args__ = (
        Index("ix_aq_student_skill_weight_aq", "aq_code"),
    )
