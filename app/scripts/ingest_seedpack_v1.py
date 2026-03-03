"""
SeedPack ingest (v1)

Reads an Excel file and loads:
- Skills
- Questions
- Career Clusters
- Key Skills
- Skill -> KeySkill map
- Careers
- Career -> KeySkill association

Design notes:
- Current DB schema uses questions.id as INTEGER PK (auto-increment).
- This script does NOT require a "question_id" column in Excel.
- Assessment API currently expects responses.question_id as a string, so we return/accept ids as strings at API layer.

Usage (inside container):
  python -m app.scripts.ingest_seedpack_v1          # dry-run validate + counts only
  python -m app.scripts.ingest_seedpack_v1 --write  # write to DB
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import pandas as pd

SEEDPACK_PATH_DEFAULT = "/app/seed/CareerPlatform_SeedPack_v1.xlsx"


@dataclass
class Counts:
    skills: int = 0
    questions: int = 0
    key_skills: int = 0
    career_clusters: int = 0
    careers: int = 0
    skill_keyskill_map: int = 0
    career_keyskill_map: int = 0


def _import_db_bits():
    # Import lazily so module import doesn't explode when running outside container.
    from app.database import SessionLocal
    from app.models import (
        Skill,
        Question,
        KeySkill,
        CareerCluster,
        Career,
        SkillKeySkillMap,
        career_keyskill_association,
    )
    return (
        SessionLocal,
        Skill,
        Question,
        KeySkill,
        CareerCluster,
        Career,
        SkillKeySkillMap,
        career_keyskill_association,
    )


def _clean_str(x: Any) -> Optional[str]:
    if x is None:
        return None
    if isinstance(x, float) and pd.isna(x):
        return None
    s = str(x).strip()
    return s if s else None


def _clean_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, float) and pd.isna(x):
        return None
    s = str(x).strip()
    if s == "":
        return None
    # allow "12.0" from excel
    try:
        return int(float(s))
    except Exception:
        return None


def _read_excel(path: str) -> Dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(path)
    dfs: Dict[str, pd.DataFrame] = {}
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        # normalize column names
        df.columns = [str(c).strip() for c in df.columns]
        dfs[sheet.strip().lower()] = df
    return dfs


def _find_sheet(dfs: Dict[str, pd.DataFrame], candidates: Tuple[str, ...]) -> Optional[pd.DataFrame]:
    for c in candidates:
        df = dfs.get(c)
        if df is not None:
            return df
    return None


def _upsert_skills(session, Skill, df_skills: pd.DataFrame) -> Dict[str, int]:
    """
    Expected columns (flexible):
      - name  (preferred)
      - skill_name (fallback)
    """
    if df_skills is None or df_skills.empty:
        return {}

    cols = {c.lower(): c for c in df_skills.columns}
    name_col = cols.get("name") or cols.get("skill_name") or cols.get("skill")

    if not name_col:
        raise ValueError("Skills sheet missing a 'name' (or 'skill_name') column")

    skill_name_to_id: Dict[str, int] = {}

    for _, row in df_skills.iterrows():
        name = _clean_str(row.get(name_col))
        if not name:
            continue

        existing = session.query(Skill).filter(Skill.name == name).first()
        if existing:
            skill_name_to_id[name] = existing.id
            continue

        obj = Skill(name=name)
        session.add(obj)
        session.flush()
        skill_name_to_id[name] = obj.id

    return skill_name_to_id


def _upsert_keyskills(session, KeySkill, df_ks: pd.DataFrame) -> Dict[str, int]:
    """
    Sheet: key_skills
    Expected columns:
      - key_skill_name (required)
      - notes (optional)
    """
    if df_ks is None or df_ks.empty:
        return {}

    cols = {c.lower(): c for c in df_ks.columns}
    name_col = cols.get("key_skill_name") or cols.get("name") or cols.get("keyskill") or cols.get("key_skill")

    if not name_col:
        raise ValueError("key_skills sheet missing 'key_skill_name' column")

    keyskill_name_to_id: Dict[str, int] = {}

    for _, row in df_ks.iterrows():
        name = _clean_str(row.get(name_col))
        if not name:
            continue

        existing = session.query(KeySkill).filter(KeySkill.name == name).first()
        if existing:
            keyskill_name_to_id[name] = existing.id
            continue

        obj = KeySkill(name=name)
        session.add(obj)
        session.flush()
        keyskill_name_to_id[name] = obj.id

    return keyskill_name_to_id


def _upsert_career_clusters(session, CareerCluster, df_cc: pd.DataFrame) -> Dict[str, int]:
    """
    Sheet: career_clusters
    Expected columns:
      - cluster_name (required)
    """
    if df_cc is None or df_cc.empty:
        return {}

    cols = {c.lower(): c for c in df_cc.columns}
    name_col = cols.get("cluster_name") or cols.get("name")

    if not name_col:
        raise ValueError("career_clusters sheet missing 'cluster_name' column")

    cluster_name_to_id: Dict[str, int] = {}

    for _, row in df_cc.iterrows():
        name = _clean_str(row.get(name_col))
        if not name:
            continue

        existing = session.query(CareerCluster).filter(CareerCluster.name == name).first()
        if existing:
            cluster_name_to_id[name] = existing.id
            continue

        obj = CareerCluster(name=name)
        session.add(obj)
        session.flush()
        cluster_name_to_id[name] = obj.id

    return cluster_name_to_id


def _upsert_careers(session, Career, df_careers: pd.DataFrame, cluster_name_to_id: Dict[str, int]) -> Dict[str, int]:
    """
    Sheet: careers
    Expected columns:
      - career_name (required)
      - cluster_name (required)
    """
    if df_careers is None or df_careers.empty:
        return {}

    cols = {c.lower(): c for c in df_careers.columns}
    career_col = cols.get("career_name") or cols.get("name")
    cluster_col = cols.get("cluster_name") or cols.get("career_cluster") or cols.get("cluster")

    if not career_col:
        raise ValueError("careers sheet missing 'career_name' column")
    if not cluster_col:
        raise ValueError("careers sheet missing 'cluster_name' column")

    career_name_to_id: Dict[str, int] = {}

    for _, row in df_careers.iterrows():
        career_name = _clean_str(row.get(career_col))
        cluster_name = _clean_str(row.get(cluster_col))
        if not career_name or not cluster_name:
            continue

        cluster_id = cluster_name_to_id.get(cluster_name)
        if cluster_id is None:
            raise ValueError(f"Career row references unknown cluster_name='{cluster_name}': {dict(row)}")

        existing = session.query(Career).filter(Career.name == career_name).first()
        if existing:
            # Keep it idempotent: update cluster if changed
            if getattr(existing, "cluster_id", None) != cluster_id:
                existing.cluster_id = cluster_id
                session.add(existing)
            career_name_to_id[career_name] = existing.id
            continue

        obj = Career(name=career_name, cluster_id=cluster_id)
        session.add(obj)
        session.flush()
        career_name_to_id[career_name] = obj.id

    return career_name_to_id


def _upsert_skill_keyskill_map(
    session,
    SkillKeySkillMap,
    df_map: pd.DataFrame,
    skill_name_to_id: Dict[str, int],
    keyskill_name_to_id: Dict[str, int],
) -> int:
    """
    Sheet: skill_keyskill_map
    Expected columns:
      - skill_name (required)
      - key_skill_name (required)
    """
    if df_map is None or df_map.empty:
        return 0

    cols = {c.lower(): c for c in df_map.columns}
    skill_col = cols.get("skill_name") or cols.get("skill")
    ks_col = cols.get("key_skill_name") or cols.get("keyskill_name") or cols.get("key_skill")

    if not skill_col or not ks_col:
        raise ValueError("skill_keyskill_map sheet missing 'skill_name' and/or 'key_skill_name' columns")

    created = 0

    for _, row in df_map.iterrows():
        skill_name = _clean_str(row.get(skill_col))
        ks_name = _clean_str(row.get(ks_col))
        if not skill_name or not ks_name:
            continue

        skill_id = skill_name_to_id.get(skill_name)
        if skill_id is None:
            raise ValueError(f"skill_keyskill_map references unknown skill_name='{skill_name}'")

        keyskill_id = keyskill_name_to_id.get(ks_name)
        if keyskill_id is None:
            raise ValueError(f"skill_keyskill_map references unknown key_skill_name='{ks_name}'")

        existing = (
            session.query(SkillKeySkillMap)
            .filter(SkillKeySkillMap.skill_id == skill_id, SkillKeySkillMap.keyskill_id == keyskill_id)
            .first()
        )
        if existing:
            continue

        obj = SkillKeySkillMap(skill_id=skill_id, keyskill_id=keyskill_id)
        session.add(obj)
        created += 1

    return created


def _upsert_career_keyskill_association(
    session,
    career_keyskill_association,
    df_map: pd.DataFrame,
    career_name_to_id: Dict[str, int],
    keyskill_name_to_id: Dict[str, int],
) -> int:
    """
    Sheet: career_keyskill_map
    Expected columns:
      - career_name (required)
      - key_skill_name (required)

    Writes to association table: career_keyskill_association
    """
    if df_map is None or df_map.empty:
        return 0

    cols = {c.lower(): c for c in df_map.columns}
    career_col = cols.get("career_name") or cols.get("career")
    ks_col = cols.get("key_skill_name") or cols.get("keyskill_name") or cols.get("key_skill")

    if not career_col or not ks_col:
        raise ValueError("career_keyskill_map sheet missing 'career_name' and/or 'key_skill_name' columns")

    created = 0

    for _, row in df_map.iterrows():
        career_name = _clean_str(row.get(career_col))
        ks_name = _clean_str(row.get(ks_col))
        if not career_name or not ks_name:
            continue

        career_id = career_name_to_id.get(career_name)
        if career_id is None:
            raise ValueError(f"career_keyskill_map references unknown career_name='{career_name}'")

        keyskill_id = keyskill_name_to_id.get(ks_name)
        if keyskill_id is None:
            raise ValueError(f"career_keyskill_map references unknown key_skill_name='{ks_name}'")

        # Idempotent insert into association table
        exists = session.execute(
            career_keyskill_association.select().where(
                (career_keyskill_association.c.career_id == career_id)
                & (career_keyskill_association.c.keyskill_id == keyskill_id)
            )
        ).first()

        if exists:
            continue

        session.execute(
            career_keyskill_association.insert().values(career_id=career_id, keyskill_id=keyskill_id)
        )
        created += 1

    return created


def _insert_questions(session, Question, df_q: pd.DataFrame, skill_name_to_id: Dict[str, int]) -> int:
    """
    Expected columns (flexible):
      - assessment_version (required)
      - skill_id (preferred) OR skill_name / skill (fallback)
      - question_text_en (required)
      - question_text_hi (optional)
      - question_text_ta (optional)
      - weight (optional, default 1)
      - group_id (optional)
      - prerequisite_qid (optional)  <-- must be integer id if used
    """
    if df_q is None or df_q.empty:
        return 0

    cols = {c.lower(): c for c in df_q.columns}

    av_col = cols.get("assessment_version")
    if not av_col:
        raise ValueError("Questions sheet missing required column: assessment_version")

    q_en_col = cols.get("question_text_en") or cols.get("question_en") or cols.get("question") or cols.get("scenario")
    if not q_en_col:
        raise ValueError("Questions sheet missing required column: question_text_en")

    skill_id_col = cols.get("skill_id")
    skill_name_col = cols.get("skill_name") or cols.get("skill")

    q_hi_col = cols.get("question_text_hi")
    q_ta_col = cols.get("question_text_ta")
    weight_col = cols.get("weight")
    group_col = cols.get("group_id")
    prereq_col = cols.get("prerequisite_qid")

    created = 0

    for _, row in df_q.iterrows():
        assessment_version = _clean_str(row.get(av_col))
        question_text_en = _clean_str(row.get(q_en_col))

        if not assessment_version or not question_text_en:
            continue

        skill_id = _clean_int(row.get(skill_id_col)) if skill_id_col else None
        if skill_id is None:
            skill_name = _clean_str(row.get(skill_name_col)) if skill_name_col else None
            if skill_name:
                skill_id = skill_name_to_id.get(skill_name)

        if skill_id is None:
            raise ValueError(f"Question row missing skill_id (or unmapped skill_name): {dict(row)}")

        obj = Question(
            assessment_version=assessment_version,
            question_text_en=question_text_en,
            question_text_hi=_clean_str(row.get(q_hi_col)) if q_hi_col else None,
            question_text_ta=_clean_str(row.get(q_ta_col)) if q_ta_col else None,
            skill_id=skill_id,
            weight=_clean_int(row.get(weight_col)) if weight_col else 1,
            group_id=_clean_str(row.get(group_col)) if group_col else None,
            prerequisite_qid=_clean_int(row.get(prereq_col)) if prereq_col else None,
        )
        session.add(obj)
        created += 1

    return created


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=SEEDPACK_PATH_DEFAULT)
    parser.add_argument("--write", action="store_true", help="Actually write to DB")
    parser.add_argument("--skip-questions", action="store_true", help="Do not insert questions (prevents duplicates)")
    args = parser.parse_args()

    (
        SessionLocal,
        Skill,
        Question,
        KeySkill,
        CareerCluster,
        Career,
        SkillKeySkillMap,
        career_keyskill_association,
    ) = _import_db_bits()

    dfs = _read_excel(args.path)

    df_skills = _find_sheet(dfs, ("skills", "skill", "student_skills"))
    df_questions = _find_sheet(dfs, ("questions", "question", "assessment_questions"))

    # NEW sheets (exact names present in your workbook)
    df_keyskills = _find_sheet(dfs, ("key_skills", "keyskills", "key_skills_v1"))
    df_clusters = _find_sheet(dfs, ("career_clusters", "clusters", "career_cluster"))
    df_careers = _find_sheet(dfs, ("careers", "career"))
    df_skill_ks_map = _find_sheet(dfs, ("skill_keyskill_map", "skill_key_skill_map"))
    df_career_ks_map = _find_sheet(dfs, ("career_keyskill_map", "career_key_skill_map"))

    # DRY RUN validation checks (skills/questions remain mandatory)
    if df_skills is None:
        raise ValueError("Could not find a Skills sheet (expected one of: skills, skill, student_skills)")
    if df_questions is None:
        raise ValueError("Could not find a Questions sheet (expected one of: questions, question, assessment_questions)")

    counts = Counts(
        skills=int(len(df_skills.index)) if df_skills is not None else 0,
        questions=int(len(df_questions.index)) if df_questions is not None else 0,
        key_skills=int(len(df_keyskills.index)) if df_keyskills is not None else 0,
        career_clusters=int(len(df_clusters.index)) if df_clusters is not None else 0,
        careers=int(len(df_careers.index)) if df_careers is not None else 0,
        skill_keyskill_map=int(len(df_skill_ks_map.index)) if df_skill_ks_map is not None else 0,
        career_keyskill_map=int(len(df_career_ks_map.index)) if df_career_ks_map is not None else 0,
    )

    print("\n✅ SeedPack DRY RUN VALIDATION PASSED")
    print(f"  Path: {args.path}")
    print("  Counts:")
    print(f"   - skills: {counts.skills}")
    print(f"   - questions: {counts.questions}")
    print(f"   - key_skills: {counts.key_skills}")
    print(f"   - career_clusters: {counts.career_clusters}")
    print(f"   - careers: {counts.careers}")
    print(f"   - skill_keyskill_map: {counts.skill_keyskill_map}")
    print(f"   - career_keyskill_map: {counts.career_keyskill_map}\n")

    if not args.write:
        return

    session = SessionLocal()
    try:
        # 1) Skills
        skill_name_to_id = _upsert_skills(session, Skill, df_skills)

        # 2) Career clusters (needed before careers)
        cluster_name_to_id = _upsert_career_clusters(session, CareerCluster, df_clusters) if df_clusters is not None else {}

        # 3) Key skills (needed before mapping tables)
        keyskill_name_to_id = _upsert_keyskills(session, KeySkill, df_keyskills) if df_keyskills is not None else {}

        # 4) Careers (needs clusters)
        career_name_to_id = _upsert_careers(session, Career, df_careers, cluster_name_to_id) if df_careers is not None else {}

        # 5) Skill -> KeySkill map
        created_skill_ks = _upsert_skill_keyskill_map(
            session, SkillKeySkillMap, df_skill_ks_map, skill_name_to_id, keyskill_name_to_id
        ) if df_skill_ks_map is not None else 0

        # 6) Career -> KeySkill association
        created_career_ks = _upsert_career_keyskill_association(
            session, career_keyskill_association, df_career_ks_map, career_name_to_id, keyskill_name_to_id
        ) if df_career_ks_map is not None else 0

        # 7) Questions
        created_q = 0
        if not args.skip_questions:
            created_q = _insert_questions(session, Question, df_questions, skill_name_to_id)

        session.commit()

        print("✅ DB WRITE COMPLETE")
        print(f"   - Skills processed (rows in seed): {counts.skills}")
        print(f"   - Career clusters processed (rows in seed): {counts.career_clusters}")
        print(f"   - Key skills processed (rows in seed): {counts.key_skills}")
        print(f"   - Careers processed (rows in seed): {counts.careers}")
        print(f"   - Skill->KeySkill links created: {created_skill_ks}")
        print(f"   - Career->KeySkill links created: {created_career_ks}")
        print(f"   - Questions created: {created_q}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
