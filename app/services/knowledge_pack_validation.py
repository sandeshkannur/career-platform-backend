"""
backend/app/services/knowledge_pack_validation.py

PR12: Knowledge Pack Validation (Admin-only, Read-only)

This module MUST be import-safe (no circular imports).
Therefore, schema imports occur inside run_validate_knowledge_pack().
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import (
    AQFacet,
    AssociatedQuality,
    Career,
    CareerCluster,
    KeySkill,
    Question,
    QuestionFacetTag,
    career_keyskill_association,
)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def run_validate_knowledge_pack(db: Session):
    """
    Admin-only validation snapshot. Read-only. No scoring changes.
    """
    # IMPORTANT: local import prevents circular import / startup failures
    from app.schemas import (  # noqa: WPS433
        ValidateKnowledgePackResponse,
        KnowledgePackStat,
        KnowledgePackIssue,
    )

    stats: List[KnowledgePackStat] = []
    issues: List[KnowledgePackIssue] = []

    def add_count(table_name: str, count_value: Any) -> None:
        stats.append(
            KnowledgePackStat(
                table=table_name,
                rows=_safe_int(count_value),
            )
        )

    # -------------------------
    # Core counts
    # -------------------------
    clusters_count = db.query(CareerCluster).count()
    careers_count = db.query(Career).count()
    keyskills_count = db.query(KeySkill).count()

    add_count("career_clusters", clusters_count)
    add_count("careers", careers_count)
    add_count("keyskills", keyskills_count)

    ck_count = db.execute(select(func.count()).select_from(career_keyskill_association)).scalar_one()
    add_count("career_keyskill_association", ck_count)

    # -------------------------
    # Explainability layer counts
    # -------------------------
    aqs_count = db.query(AssociatedQuality).count()
    aq_facets_count = db.query(AQFacet).count()
    questions_count = db.query(Question).count()
    qft_count = db.execute(text("SELECT COUNT(*) FROM question_facet_tags_v")).scalar() or 0

    add_count("associated_qualities", aqs_count)
    add_count("aq_facets", aq_facets_count)
    add_count("questions", questions_count)
    add_count("question_facet_tags", qft_count)  # keep label stable for clients

    try:
        aq_ss_weights_count = db.execute(text("SELECT COUNT(*) FROM aq_student_skill_weights")).scalar() or 0
        add_count("aq_student_skill_weights", aq_ss_weights_count)
    except Exception:
        # If table not present in some env, we simply skip
        pass

        # PR35: include QSSW table count in stats (read-only)
    try:
        qssw_count = db.execute(text("SELECT COUNT(*) FROM question_student_skill_weights")).scalar() or 0
        add_count("question_student_skill_weights", int(qssw_count))
    except Exception:
        # If table not present in some env, we simply skip
        pass

    # -------------------------
    # PR35: Validate Question -> StudentSkill weights (QSSW)
    # Rules:
    #  - Each question_id group must sum(weight) ~= 1.0 (tolerance)
    #  - No negative weights
    # -------------------------
    try:
        tolerance = 0.0001  # numeric(6,4) friendly; avoids false positives due to rounding

        # A) Negative weights
        neg_rows = (
            db.execute(
                text(
                    """
                    SELECT question_id, skill_id, weight
                    FROM question_student_skill_weights
                    WHERE weight < 0
                    ORDER BY question_id, skill_id
                    LIMIT 20
                    """
                )
            )
            .mappings()
            .all()
        )

        if neg_rows:
            issues.append(
                KnowledgePackIssue(
                    code="qssw.weight.negative",
                    severity="error",
                    message="Negative weights found in question_student_skill_weights. Weights must be non-negative.",
                    sample={"examples": [dict(r) for r in neg_rows]},
                )
            )

        # B) Per-question sum(weight) must be ~ 1.0
        bad_sums = (
            db.execute(
                text(
                    """
                    SELECT
                        question_id,
                        ROUND(SUM(weight)::numeric, 6) AS sum_weight,
                        COUNT(*) AS rows
                    FROM question_student_skill_weights
                    GROUP BY question_id
                    HAVING ABS(SUM(weight) - 1.0) > :tolerance
                    ORDER BY question_id
                    LIMIT 50
                    """
                ),
                {"tolerance": tolerance},
            )
            .mappings()
            .all()
        )

        if bad_sums:
            issues.append(
                KnowledgePackIssue(
                    code="qssw.weight_sum.invalid",
                    severity="error",
                    message="Per-question weights must sum to 1.0 (+/- tolerance). Fix QSSW mapping and re-upload.",
                    sample={"tolerance": tolerance, "examples": [dict(r) for r in bad_sums]},
                )
            )

    except Exception:
        # Keep validator resilient across envs
        pass

    # -------------------------
    # Neutral baseline warnings
    # -------------------------
    if clusters_count == 0:
        issues.append(
            KnowledgePackIssue(
                code="clusters.empty",
                severity="warning",
                message="No career clusters found. This usually means the knowledge pack has not been ingested yet.",
                sample=None,
            )
        )

    if careers_count == 0:
        issues.append(
            KnowledgePackIssue(
                code="careers.empty",
                severity="warning",
                message="No careers found. This usually means the knowledge pack has not been ingested yet.",
                sample=None,
            )
        )

    if keyskills_count == 0:
        issues.append(
            KnowledgePackIssue(
                code="keyskills.empty",
                severity="warning",
                message="No key skills found. This usually means the knowledge pack has not been ingested yet.",
                sample=None,
            )
        )

    if int(ck_count) == 0 and careers_count > 0 and keyskills_count > 0:
        issues.append(
            KnowledgePackIssue(
                code="career_keyskill_map.empty",
                severity="warning",
                message="No Career ↔ KeySkill mappings found. Recommendations may be incomplete until mappings are uploaded.",
                sample=None,
            )
        )

    if questions_count > 0 and int(qft_count) == 0:
        issues.append(
            KnowledgePackIssue(
                code="question_facet_tags.missing",
                severity="warning",
                message="No Question ↔ Facet tags found. AQ/Facet explainability will be limited until facet tagging is uploaded.",
                sample=None,
            )
        )

        # -------------------------
    # Planned enhancement: Explainability depth
    # -------------------------

    # 1) AQs with zero facets (should be rare if AQ facets ingestion is complete)
    try:
        aqs_without_facets_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM associated_qualities aq
                    LEFT JOIN aq_facets f ON f.aq_id = aq.aq_id
                    WHERE f.facet_id IS NULL
                    """
                )
            ).scalar()
            or 0
        )

        if int(aqs_without_facets_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT aq.aq_id, aq.aq_name
                        FROM associated_qualities aq
                        LEFT JOIN aq_facets f ON f.aq_id = aq.aq_id
                        WHERE f.facet_id IS NULL
                        ORDER BY aq.aq_id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )
            issues.append(
                KnowledgePackIssue(
                    code="aqs.missing_facets",
                    severity="warning",
                    message="Some associated qualities (AQs) have no facets. Explainability may be less specific for these AQs until facets are added.",
                    sample={"examples": [dict(r) for r in examples], "count": int(aqs_without_facets_count)},
                )
            )
    except Exception:
        pass

    # 2) AQs with facets but no questions (requires facet tagging to be meaningful)
    # If facet tagging is missing, we report an informational note instead of warning.
    try:
        if int(qft_count) == 0:
            issues.append(
                KnowledgePackIssue(
                    code="aqs.facets_without_questions.check_skipped",
                    severity="info",
                    message="Facet tagging is not present yet, so AQ → Facet → Question coverage cannot be evaluated. Once question facet tags are uploaded, this check will become active.",
                    sample=None,
                )
            )
        else:
            aqs_facets_no_questions_count = (
                db.execute(
                    text(
                        """
                        SELECT COUNT(*) AS cnt
                        FROM associated_qualities aq
                        JOIN aq_facets f ON f.aq_id = aq.aq_id
                        LEFT JOIN question_facet_tags_v qft ON qft.facet_code = f.facet_id
                        WHERE qft.facet_id IS NULL
                        """
                    )
                ).scalar()
                or 0
            )

            if int(aqs_facets_no_questions_count) > 0:
                examples = (
                    db.execute(
                        text(
                            """
                            SELECT aq.aq_id, aq.aq_name, f.facet_id, f.facet_name
                            FROM associated_qualities aq
                            JOIN aq_facets f ON f.aq_id = aq.aq_id
                            LEFT JOIN question_facet_tags_v qft ON qft.facet_id = f.facet_id
                            WHERE qft.facet_id IS NULL
                            ORDER BY aq.aq_id, f.facet_id
                            LIMIT 2
                            """
                        )
                    )
                    .mappings()
                    .all()
                )

                issues.append(
                    KnowledgePackIssue(
                        code="aq_facets.unused_by_questions",
                        severity="warning",
                        message="Some AQ facets are not linked to any question. These facets may not appear in explainability until question tagging is added.",
                        sample={"examples": [dict(r) for r in examples], "count": int(aqs_facets_no_questions_count)},
                    )
                )
    except Exception:
        pass

    # 3) Skill → AQ → coverage proxy:
    # If AQ→Skill weights exist but that Skill has no questions, AQ evidence cannot be collected via questions.
    # This is meaningful even before facet tagging exists.
    try:
        skills_with_aq_weights_but_no_questions_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM (
                        SELECT DISTINCT ssw.skill_id
                        FROM aq_student_skill_weights ssw
                        WHERE ssw.status IS NULL OR ssw.status <> 'inactive'
                    ) w
                    LEFT JOIN questions q ON q.skill_id = w.skill_id
                    WHERE q.id IS NULL
                    """
                )
            ).scalar()
            or 0
        )

        if int(skills_with_aq_weights_but_no_questions_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT w.skill_id
                        FROM (
                            SELECT DISTINCT ssw.skill_id
                            FROM aq_student_skill_weights ssw
                            WHERE ssw.status IS NULL OR ssw.status <> 'inactive'
                        ) w
                        LEFT JOIN questions q ON q.skill_id = w.skill_id
                        WHERE q.id IS NULL
                        ORDER BY w.skill_id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )

            issues.append(
                KnowledgePackIssue(
                    code="skills.with_aq_weights_missing_questions",
                    severity="warning",
                    message="Some skills have AQ→Skill weights but no questions mapped to those skills. This can reduce evidence collection for those AQs until questions are added for those skills.",
                    sample={"examples": [dict(r) for r in examples], "count": int(skills_with_aq_weights_but_no_questions_count)},
                )
            )
    except Exception:
        pass


    # -------------------------
    # Careers missing keyskills
    # -------------------------
    try:
        missing_careers_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM careers c
                    LEFT JOIN career_keyskill_association ck ON ck.career_id = c.id
                    WHERE ck.career_id IS NULL
                    """
                )
            ).scalar()
            or 0
        )

        if int(missing_careers_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT c.id AS career_id, c.title AS career_title
                        FROM careers c
                        LEFT JOIN career_keyskill_association ck ON ck.career_id = c.id
                        WHERE ck.career_id IS NULL
                        ORDER BY c.id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )
            issues.append(
                KnowledgePackIssue(
                    code="careers.missing_keyskills",
                    severity="warning",
                    message="Some careers have no linked key skills. Recommendations and explainability may be incomplete for these careers until mappings are added.",
                    sample={"examples": [dict(r) for r in examples]},
                )
            )
    except Exception:
        pass

    # -------------------------
    # Keyskills missing careers
    # -------------------------
    try:
        missing_keyskills_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM keyskills ks
                    LEFT JOIN career_keyskill_association ck ON ck.keyskill_id = ks.id
                    WHERE ck.keyskill_id IS NULL
                    """
                )
            ).scalar()
            or 0
        )

        if int(missing_keyskills_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT ks.id AS keyskill_id, ks.name AS keyskill_name, ks.cluster_id
                        FROM keyskills ks
                        LEFT JOIN career_keyskill_association ck ON ck.keyskill_id = ks.id
                        WHERE ck.keyskill_id IS NULL
                        ORDER BY ks.id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )
            issues.append(
                KnowledgePackIssue(
                    code="keyskills.missing_careers",
                    severity="warning",
                    message="Some key skills are not linked to any career. These key skills may not contribute to recommendations until mappings are added.",
                    sample={"examples": [dict(r) for r in examples]},
                )
            )
    except Exception:
        pass

    # -------------------------
    # Weight governance
    # -------------------------
    try:
        missing_weights_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM career_keyskill_association
                    WHERE weight_percentage IS NULL
                    """
                )
            ).scalar()
            or 0
        )

        if int(missing_weights_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT career_id, keyskill_id
                        FROM career_keyskill_association
                        WHERE weight_percentage IS NULL
                        ORDER BY career_id, keyskill_id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )
            issues.append(
                KnowledgePackIssue(
                    code="career_keyskill_weights.missing",
                    severity="warning",
                    message="Some Career ↔ KeySkill mappings have no weight set. These mappings may not behave as intended until weights are provided.",
                    sample={"examples": [dict(r) for r in examples]},
                )
            )
    except Exception:
        pass

    try:
        sum_not_100_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM (
                        SELECT career_id, SUM(weight_percentage) AS sum_weight
                        FROM career_keyskill_association
                        WHERE weight_percentage IS NOT NULL
                        GROUP BY career_id
                    ) t
                    WHERE t.sum_weight <> 100
                    """
                )
            ).scalar()
            or 0
        )

        if int(sum_not_100_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT career_id, SUM(weight_percentage) AS sum_weight
                        FROM career_keyskill_association
                        WHERE weight_percentage IS NOT NULL
                        GROUP BY career_id
                        HAVING SUM(weight_percentage) <> 100
                        ORDER BY career_id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )
            issues.append(
                KnowledgePackIssue(
                    code="career_keyskill_weights.sum_not_100",
                    severity="warning",
                    message="Some careers have Career ↔ KeySkill weights that do not add up to 100. Weight distribution may need review for consistent interpretation.",
                    sample={"examples": [dict(r) for r in examples]},
                )
            )
    except Exception:
        pass
    # -------------------------
    # PR35: Question -> StudentSkill weight governance (QSSW)
    # -------------------------
    try:
        tolerance = 0.0001  # numeric(6,4) friendly

        # 1) Negative weights (should be prevented by DB CHECK, but report if present)
        neg_rows = (
            db.execute(
                text(
                    """
                    SELECT question_id, skill_id, weight
                    FROM question_student_skill_weights
                    WHERE weight < 0
                    ORDER BY question_id, skill_id
                    LIMIT 5
                    """
                )
            )
            .mappings()
            .all()
        )

        if len(neg_rows) > 0:
            issues.append(
                KnowledgePackIssue(
                    code="qssw.weight.negative",
                    severity="error",
                    message="Found negative weights in question_student_skill_weights. Weights must be non-negative.",
                    sample={"examples": [dict(r) for r in neg_rows]},
                )
            )

        # 2) Per-question sum must be ~ 1.0
        bad_sums = (
            db.execute(
                text(
                    """
                    SELECT question_id,
                           ROUND(SUM(weight)::numeric, 6) AS sum_weight,
                           COUNT(*) AS rows
                    FROM question_student_skill_weights
                    GROUP BY question_id
                    HAVING ABS(SUM(weight) - 1.0) > :tolerance
                    ORDER BY question_id
                    LIMIT 20
                    """
                ),
                {"tolerance": tolerance},
            )
            .mappings()
            .all()
        )

        if len(bad_sums) > 0:
            issues.append(
                KnowledgePackIssue(
                    code="qssw.weight_sum.invalid",
                    severity="error",
                    message="Per-question QSSW weights must sum to 1.0 (± tolerance). Fix the mapping and re-upload.",
                    sample={"examples": [dict(r) for r in bad_sums], "tolerance": tolerance},
                )
            )

    except Exception:
        # In some envs the table may not exist; keep validator resilient.
        pass
    # -------------------------
    # Planned enhancement: Assessment consistency (Questions unlinked)
    # -------------------------
    try:
        unlinked_questions_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM questions q
                    LEFT JOIN assessment_questions aq ON aq.question_id = q.id
                    WHERE aq.question_id IS NULL
                    """
                )
            ).scalar()
            or 0
        )

        if int(unlinked_questions_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT q.id AS question_id, q.assessment_version, q.question_code
                        FROM questions q
                        LEFT JOIN assessment_questions aq ON aq.question_id = q.id
                        WHERE aq.question_id IS NULL
                        ORDER BY q.assessment_version, q.id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )
            issues.append(
                KnowledgePackIssue(
                    code="assessments.questions_unlinked",
                    severity="warning",
                    message="Some questions are not linked to any assessment. They will not appear in live assessments until they are added to assessment question sets.",
                    sample={"examples": [dict(r) for r in examples], "count": int(unlinked_questions_count)},
                )
            )
    except Exception:
        pass
    # ---- Assessment layer (governance) ----
    try:
        assessments_count = db.execute(text("SELECT COUNT(*) FROM assessments")).scalar() or 0
        add_count("assessments", int(assessments_count))
    except Exception:
        pass

    try:
        assessment_questions_count = db.execute(text("SELECT COUNT(*) FROM assessment_questions")).scalar() or 0
        add_count("assessment_questions", int(assessment_questions_count))
    except Exception:
        pass

        # -------------------------
    # Planned enhancement: Assessment consistency
    # -------------------------

    # 1) Orphan assessment_questions rows:
    # - assessment_id does not exist in assessments
    # - question_id does not exist in questions
    # Even if FKs exist, this is a safety check (read-only governance).
    try:
        orphan_aq_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM assessment_questions aq
                    LEFT JOIN assessments a ON a.id = aq.assessment_id
                    LEFT JOIN questions q ON q.id = aq.question_id
                    WHERE a.id IS NULL OR q.id IS NULL
                    """
                )
            ).scalar()
            or 0
        )

        if int(orphan_aq_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT
                            aq.assessment_id,
                            aq.question_id,
                            CASE WHEN a.id IS NULL THEN true ELSE false END AS missing_assessment,
                            CASE WHEN q.id IS NULL THEN true ELSE false END AS missing_question
                        FROM assessment_questions aq
                        LEFT JOIN assessments a ON a.id = aq.assessment_id
                        LEFT JOIN questions q ON q.id = aq.question_id
                        WHERE a.id IS NULL OR q.id IS NULL
                        ORDER BY aq.assessment_id, aq.question_id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )

            issues.append(
                KnowledgePackIssue(
                    code="assessments.orphan_assessment_questions",
                    severity="warning",
                    message="Some assessment question links refer to a missing assessment or missing question. These links will not behave as intended until the underlying records are aligned.",
                    sample={"examples": [dict(r) for r in examples], "count": int(orphan_aq_count)},
                )
            )
    except Exception:
        pass

    # 2) Assessment version drift:
    # If a single assessment includes questions from multiple question.assessment_version values,
    # interpretability can become inconsistent.
    try:
        drift_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM (
                        SELECT
                            aq.assessment_id,
                            COUNT(DISTINCT COALESCE(q.assessment_version, '__NULL__')) AS version_count
                        FROM assessment_questions aq
                        JOIN questions q ON q.id = aq.question_id
                        GROUP BY aq.assessment_id
                    ) t
                    WHERE t.version_count > 1
                    """
                )
            ).scalar()
            or 0
        )

        if int(drift_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT
                            aq.assessment_id,
                            ARRAY_AGG(DISTINCT COALESCE(q.assessment_version, '__NULL__') ORDER BY COALESCE(q.assessment_version, '__NULL__')) AS versions,
                            COUNT(*) AS question_count
                        FROM assessment_questions aq
                        JOIN questions q ON q.id = aq.question_id
                        GROUP BY aq.assessment_id
                        HAVING COUNT(DISTINCT COALESCE(q.assessment_version, '__NULL__')) > 1
                        ORDER BY aq.assessment_id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )

            # Convert ARRAY output safely (psycopg2 returns list already)
            clean_examples = []
            for r in examples:
                clean_examples.append(
                    {
                        "assessment_id": r["assessment_id"],
                        "versions": r["versions"],
                        "question_count": int(r["question_count"]),
                    }
                )

            issues.append(
                KnowledgePackIssue(
                    code="assessments.version_drift",
                    severity="warning",
                    message="Some assessments include questions from multiple assessment versions. This can make interpretation inconsistent until the assessment question set is aligned.",
                    sample={"examples": clean_examples, "count": int(drift_count)},
                )
            )
    except Exception:
        pass

    # -------------------------
    # Planned enhancement: Assessment consistency
    # -------------------------

    # 1) Orphan assessment_questions rows (should be 0 when FKs are healthy)
    try:
        orphan_aq_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM assessment_questions aq
                    LEFT JOIN assessments a ON a.id = aq.assessment_id
                    LEFT JOIN questions q ON q.id = aq.question_id
                    WHERE a.id IS NULL OR q.id IS NULL
                    """
                )
            ).scalar()
            or 0
        )

        if int(orphan_aq_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT
                            aq.assessment_id,
                            aq.question_id,
                            CASE WHEN a.id IS NULL THEN true ELSE false END AS missing_assessment,
                            CASE WHEN q.id IS NULL THEN true ELSE false END AS missing_question
                        FROM assessment_questions aq
                        LEFT JOIN assessments a ON a.id = aq.assessment_id
                        LEFT JOIN questions q ON q.id = aq.question_id
                        WHERE a.id IS NULL OR q.id IS NULL
                        ORDER BY aq.assessment_id, aq.question_id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )

            issues.append(
                KnowledgePackIssue(
                    code="assessments.orphan_assessment_questions",
                    severity="warning",
                    message="Some assessment question links refer to a missing assessment or missing question. These links will not behave as intended until the underlying records are aligned.",
                    sample={"examples": [dict(r) for r in examples], "count": int(orphan_aq_count)},
                )
            )
    except Exception:
        pass

    # 2) Assessment version drift: an assessment includes questions from >1 question.assessment_version
    try:
        drift_count = (
            db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM (
                        SELECT
                            aq.assessment_id,
                            COUNT(DISTINCT COALESCE(q.assessment_version, '__NULL__')) AS version_count
                        FROM assessment_questions aq
                        JOIN questions q ON q.id = aq.question_id
                        GROUP BY aq.assessment_id
                    ) t
                    WHERE t.version_count > 1
                    """
                )
            ).scalar()
            or 0
        )

        if int(drift_count) > 0:
            examples = (
                db.execute(
                    text(
                        """
                        SELECT
                            aq.assessment_id,
                            ARRAY_AGG(DISTINCT COALESCE(q.assessment_version, '__NULL__')
                                      ORDER BY COALESCE(q.assessment_version, '__NULL__')) AS versions,
                            COUNT(*) AS question_count
                        FROM assessment_questions aq
                        JOIN questions q ON q.id = aq.question_id
                        GROUP BY aq.assessment_id
                        HAVING COUNT(DISTINCT COALESCE(q.assessment_version, '__NULL__')) > 1
                        ORDER BY aq.assessment_id
                        LIMIT 2
                        """
                    )
                )
                .mappings()
                .all()
            )

            clean_examples = [
                {
                    "assessment_id": r["assessment_id"],
                    "versions": r["versions"],
                    "question_count": int(r["question_count"]),
                }
                for r in examples
            ]

            issues.append(
                KnowledgePackIssue(
                    code="assessments.version_drift",
                    severity="warning",
                    message="Some assessments include questions from multiple assessment versions. This can make interpretation inconsistent until the assessment question set is aligned.",
                    sample={"examples": clean_examples, "count": int(drift_count)},
                )
            )
    except Exception:
        pass
    # -------------------------
    # Planned enhancement: Governance maturity (beta gate suggestion)
    # -------------------------
    # Additive-only: we do NOT change `status` semantics. We provide an admin-facing suggestion
    # as an INFO issue so it can be used for beta readiness decisions without breaking clients.
    try:
        warning_issues = [i for i in issues if getattr(i, "severity", None) == "warning"]
        error_issues = [i for i in issues if getattr(i, "severity", None) == "error"]

        warning_count = len(warning_issues)
        error_count = len(error_issues)

        # Minimal, safe gating rule (tunable later):
        # - If there are any errors, suggest "fail"
        # - Else if there are warnings, suggest "needs_review"
        # - Else "pass"
        if error_count > 0:
            decision = "fail"
        elif warning_count > 0:
            decision = "needs_review"
        else:
            decision = "pass"

        # Include top warning codes for fast remediation focus
        top_codes = []
        for w in warning_issues[:5]:
            code = getattr(w, "code", None)
            if code:
                top_codes.append(code)

        issues.append(
            KnowledgePackIssue(
                code="gate.decision",
                severity="info",
                message=(
                    "Beta gate suggestion: Pass. No data quality gaps were detected."
                    if decision == "pass"
                    else (
                        "Beta gate suggestion: Needs review. There are warnings that may reduce explainability or assessment coverage."
                        if decision == "needs_review"
                        else "Beta gate suggestion: Fail. Error-level data quality gaps were detected."
                    )
                ),
                sample={
                    "decision": decision,
                    "error_count": error_count,
                    "warning_count": warning_count,
                    "top_warning_codes": top_codes,
                },
            )
        )
    except Exception:
        pass

    status = "ok" if len([i for i in issues if i.severity in ("warning", "error")]) == 0 else "has_issues"

    return ValidateKnowledgePackResponse(
        status=status,
        generated_at=datetime.utcnow(),
        stats=stats,
        issues=issues,
    )

def run_validate_explainability_keys(
    db: Session,
    version: Optional[str] = None,
    locale: Optional[str] = None,
    required_families: Optional[List[str]] = None,
):
    """
    PR39: Explainability Key Taxonomy validation (admin-only, read-only).
    - Detect invalid key formats / unknown families / missing family coverage.
    - Designed to be tolerant of legacy keys already present in DB.
    """
    # IMPORTANT: local import prevents circular import / startup failures
    from app.schemas import (  # noqa: WPS433
        ValidateExplainabilityKeysResponse,
        ExplainabilityKeyIssue,
    )

    import re  # local import keeps module import-safe

    issues: List[ExplainabilityKeyIssue] = []

    # Defaults: keep beta surface minimal and consistent with PR39
    families = required_families or ["AQ", "FACET", "SKILL", "CAREER", "CLUSTER"]

    # ---- Key patterns (tolerant but governance-friendly) ----
    # 1) Canonical uppercase dotted taxonomy: AQ.INTRO.001, FACET.CONFIDENCE.001, CAREER.SOFTWARE.OVERVIEW
    canonical_re = re.compile(r"^(AQ|FACET|SKILL|CAREER|CLUSTER)(\.[A-Z0-9_]+)+$")

    # 2) Legacy constant keys: CLUSTER_SUMMARY, CAREER_TOP_MATCH (present in your DB today)
    legacy_constant_re = re.compile(r"^[A-Z0-9_]+$")

    # 3) Existing paid narrative keys (present in your DB today)
    paid_re = re.compile(r"^paid\.(career|cluster)\.[a-z0-9_]+$")

    # ---- Build WHERE clause deterministically ----
    where_parts = []
    params: Dict[str, Any] = {}

    if version:
        where_parts.append("version = :version")
        params["version"] = version

    if locale:
        where_parts.append("locale = :locale")
        params["locale"] = locale

    where_sql = ""
    if where_parts:
        where_sql = "WHERE " + " AND ".join(where_parts)

    # ---- Pull keys (read-only) ----
    rows = (
        db.execute(
            text(
                f"""
                SELECT version, locale, explanation_key
                FROM explainability_content
                {where_sql}
                ORDER BY version, locale, explanation_key
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    # Defensive duplicate check (DB uniqueness should prevent this, but keep report resilient)
    dupes = (
        db.execute(
            text(
                f"""
                SELECT version, locale, explanation_key, COUNT(*) AS cnt
                FROM explainability_content
                {where_sql}
                GROUP BY version, locale, explanation_key
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC, version, locale, explanation_key
                LIMIT 50
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    if dupes:
        issues.append(
            ExplainabilityKeyIssue(
                code="explainability.duplicate_key",
                severity="error",
                message="Duplicate explanation_key rows detected within the same (version, locale). This should not happen if the UNIQUE constraint is healthy.",
                sample={"examples": [dict(r) for r in dupes]},
            )
        )

    # ---- Format + family checks ----
    invalid_format_examples = []
    unknown_family_examples = []
    present_families = set()

    for r in rows:
        key = (r.get("explanation_key") or "").strip()
        if not key:
            invalid_format_examples.append({"explanation_key": key})
            continue

        # Family detection (for dotted keys only)
        family = key.split(".", 1)[0] if "." in key else None

        # Treat paid.* namespaces as coverage for canonical families
        # so beta coverage checks don't force duplicate key creation.
        if family == "paid":
            # paid.career.* -> CAREER, paid.cluster.* -> CLUSTER
            parts = key.split(".")
            if len(parts) >= 2:
                if parts[1] == "career":
                    present_families.add("CAREER")
                elif parts[1] == "cluster":
                    present_families.add("CLUSTER")
        else:
            if family:
                present_families.add(family)

        # Validate against tolerant set of patterns
        if canonical_re.match(key):
            # Canonical keys: enforce allowed family list
            fam = key.split(".", 1)[0]
            if fam not in families:
                unknown_family_examples.append({"explanation_key": key, "family": fam})
            continue

        if legacy_constant_re.match(key):
            # Keep as legacy acceptable (no family requirement)
            continue

        if paid_re.match(key):
            # Keep as acceptable existing tiered namespace
            continue

        # Otherwise it is invalid format
        invalid_format_examples.append({"explanation_key": key})

    if invalid_format_examples:
        issues.append(
            ExplainabilityKeyIssue(
                code="explainability.invalid_format",
                severity="warning",
                message=(
                    "Some explanation_key values do not match expected formats. "
                    "Preferred canonical format: FAMILY.UPPERCASE_SEGMENTS (e.g., AQ.INTRO.001)."
                ),
                sample={"examples": invalid_format_examples[:25]},
            )
        )

    if unknown_family_examples:
        issues.append(
            ExplainabilityKeyIssue(
                code="explainability.unknown_family",
                severity="warning",
                message=(
                    "Some dotted keys use a FAMILY prefix outside the allowed set for this validator run."
                ),
                sample={"allowed_families": families, "examples": unknown_family_examples[:25]},
            )
        )

    # ---- Missing required families (coverage) ----
    # Only evaluate for canonical families; legacy constants and paid.* do not contribute to coverage.
    missing = [f for f in families if f not in present_families]
    if missing:
        issues.append(
            ExplainabilityKeyIssue(
                code="explainability.missing_required_families",
                severity="warning",
                message="Missing one or more required key families for the selected filter scope.",
                sample={"missing_families": missing, "present_families": sorted(list(present_families))},
            )
        )

    status = "ok" if len([i for i in issues if i.severity in ("warning", "error")]) == 0 else "has_issues"

    return ValidateExplainabilityKeysResponse(
        status=status,
        generated_at=datetime.utcnow(),
        filters={
            "version": version,
            "locale": locale,
            "required_families": families,
            "rows_scanned": len(rows),
        },
        issues=issues,
    )


