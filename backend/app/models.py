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
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB  # ✅ for JSONB columns

from .database import Base


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
# Skill domain
# =========================================================

class Skill(Base):
    """
    Skill – individual skills.
    """
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)


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


# =========================================================
# Questions (assessment item bank)
# =========================================================

class Question(Base):
    """
    Question – multilingual + skill mapping + branching.
    """
    __tablename__ = "questions"

    id = Column(String, primary_key=True)
    assessment_version = Column(String, nullable=False, index=True)

    question_text_en = Column(String, nullable=False)
    question_text_hi = Column(String)
    question_text_ta = Column(String)

    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False)

    weight = Column(Integer, default=1)
    group_id = Column(String)

    prerequisite_qid = Column(String, ForeignKey("questions.id"), nullable=True)

    skill = relationship("Skill", backref="questions")
    prerequisite = relationship("Question", remote_side=[id], backref="dependents")


# =========================================================
# Assessment engine tables
# =========================================================

class Assessment(Base):
    """
    Assessment – per-user assessment attempt.
    """
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    responses = relationship("AssessmentResponse", back_populates="assessment")
    result = relationship("AssessmentResult", uselist=False, back_populates="assessment")


class AssessmentResponse(Base):
    """
    AssessmentResponse – raw answers captured per question.
    """
    __tablename__ = "assessment_responses"

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    question_id = Column(String, nullable=False)
    answer = Column(String, nullable=False)

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
    recommended_careers = Column(JSONB, nullable=True)

    # per-skill tiers/levels produced by scoring/analytics
    # Example: {"Creativity": "Intermediate", "Numerical Reasoning": "Advanced"}
    skill_tiers = Column(JSONB, nullable=True)

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

    computed_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("assessment_id", "scoring_config_version", "skill_id", name="uq_assess_skill_ver"),
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

    payload_json = Column(JSONB, nullable=False)
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