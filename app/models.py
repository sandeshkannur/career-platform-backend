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

from sqlalchemy import UniqueConstraint
from sqlalchemy.sql import func

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

