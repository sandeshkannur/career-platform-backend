# backend/app/services/evidence.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


FACET_EVIDENCE_SQL = text("""
WITH answered AS (
  SELECT
    ar.assessment_id,
    q.assessment_version,
    q.question_code
  FROM assessment_responses ar
  JOIN questions q
    ON q.id::text = ar.question_id
  WHERE ar.assessment_id = :assessment_id
),
tagged AS (
  SELECT
    a.assessment_id,
    a.assessment_version,
    a.question_code,
    qft.facet_code
  FROM answered a
  JOIN question_facet_tags_v qft
    ON qft.assessment_version = a.assessment_version
   AND qft.question_code = a.question_code
),
facet_meta AS (
  SELECT
    t.assessment_id,
    t.assessment_version,
    t.facet_code,
    f.name_en AS facet_name_en,
    f.aq_code,
    aq.name_en AS aq_name_en,
    t.question_code
  FROM tagged t
  JOIN aq_facets_v f
    ON f.assessment_version = t.assessment_version
   AND f.facet_code = t.facet_code
  JOIN associated_qualities_v aq
    ON aq.assessment_version = t.assessment_version
   AND aq.aq_code = f.aq_code
)
SELECT
  facet_code,
  facet_name_en,
  aq_code,
  aq_name_en,
  COUNT(*) AS evidence_count,
  ARRAY_AGG(question_code ORDER BY question_code) AS question_codes
FROM facet_meta
GROUP BY facet_code, facet_name_en, aq_code, aq_name_en
ORDER BY evidence_count DESC, aq_code, facet_code;
""")


AQ_EVIDENCE_SQL = text("""
WITH answered AS (
  SELECT
    ar.assessment_id,
    q.assessment_version,
    q.question_code
  FROM assessment_responses ar
  JOIN questions q
    ON q.id::text = ar.question_id
  WHERE ar.assessment_id = :assessment_id
),
tagged AS (
  SELECT
    a.assessment_id,
    a.assessment_version,
    a.question_code,
    qft.facet_code
  FROM answered a
  JOIN question_facet_tags_v qft
    ON qft.assessment_version = a.assessment_version
   AND qft.question_code = a.question_code
),
facet_meta AS (
  SELECT
    t.assessment_version,
    f.aq_code,
    aq.name_en AS aq_name_en,
    t.facet_code,
    t.question_code
  FROM tagged t
  JOIN aq_facets_v f
    ON f.assessment_version = t.assessment_version
   AND f.facet_code = t.facet_code
  JOIN associated_qualities_v aq
    ON aq.assessment_version = t.assessment_version
   AND aq.aq_code = f.aq_code
)
SELECT
  aq_code,
  aq_name_en,
  COUNT(*) AS evidence_count,
  ARRAY_AGG(DISTINCT facet_code ORDER BY facet_code) AS facet_codes,
  ARRAY_AGG(question_code ORDER BY question_code) AS question_codes
FROM facet_meta
GROUP BY aq_code, aq_name_en
ORDER BY evidence_count DESC, aq_code;
""")


def compute_assessment_evidence(db: Session, assessment_id: int) -> dict:
    """
    PR5: Computed-on-read evidence block.
    Traceability:
      assessment_responses -> questions -> question_facet_tags_v -> aq_facets_v -> associated_qualities_v
    No scoring changes; additive only.
    """
    facet_rows = db.execute(FACET_EVIDENCE_SQL, {"assessment_id": assessment_id}).mappings().all()
    aq_rows = db.execute(AQ_EVIDENCE_SQL, {"assessment_id": assessment_id}).mappings().all()

    facet_evidence = [
        {
            "facet_code": r["facet_code"],
            "facet_name_en": r["facet_name_en"],
            "aq_code": r["aq_code"],
            "aq_name_en": r["aq_name_en"],
            "evidence_count": int(r["evidence_count"]),
            "question_codes": list(r["question_codes"] or []),
        }
        for r in facet_rows
    ]

    aq_evidence_summary = [
        {
            "aq_code": r["aq_code"],
            "aq_name_en": r["aq_name_en"],
            "evidence_count": int(r["evidence_count"]),
            "facet_codes": list(r["facet_codes"] or []),
            "question_codes": list(r["question_codes"] or []),
        }
        for r in aq_rows
    ]

    return {
        "facet_evidence": facet_evidence,
        "aq_evidence_summary": aq_evidence_summary,
    }
