# backend/app/services/explanations.py

from sqlalchemy.orm import Session
from sqlalchemy import select
from app import models
from app.services.scoring import (
    compute_career_scores,
    compute_cluster_scores,
    get_student_keyskill_scores,
)


# --------------------------------------------------
# Template-based explanation builders
# --------------------------------------------------

def explain_cluster(cluster_obj, score, top_keyskills, band_breakdown=None):
    """
    Build natural-language explanation for a cluster, including
    how the student's strengths are distributed across
    core / supporting / auxiliary skills (band_breakdown).
    """
    if top_keyskills:
        ks = ", ".join(k.name for k in top_keyskills)
    else:
        ks = "your overall profile"

    base = (
        f"You have a {score}% match with the {cluster_obj.name} cluster, "
        f"mainly due to strengths in {ks}."
    )

    if band_breakdown:
        parts = []
        core = band_breakdown.get("core")
        supporting = band_breakdown.get("supporting")
        auxiliary = band_breakdown.get("auxiliary")

        if core is not None:
            parts.append(f"core skills ({core}%)")
        if supporting is not None:
            parts.append(f"supporting skills ({supporting}%)")
        if auxiliary is not None:
            parts.append(f"auxiliary skills ({auxiliary}%)")

        if parts:
            base += " Within this cluster, your strengths are distributed across " + ", ".join(parts) + "."

    return base


def explain_career(career_obj, score, top_keyskills):
    if top_keyskills:
        ks = ", ".join(k.name for k in top_keyskills)
    else:
        ks = "relevant skills"
    return (
        f"You have a {score}% match with the career '{career_obj.title}'. "
        f"Key contributing skills: {ks}."
    )


# --------------------------------------------------
# Full explanation builder – used by /paid-analytics
# --------------------------------------------------

def build_full_explanation(db: Session, student_id: int):
    """
    Computes:
        - career_scores
        - cluster_scores
        - top contributing keyskills
        - cluster band breakdown (core / supporting / auxiliary)
        - explanation strings

    Returns:
        {
            "clusters": [...],
            "careers": [...]
        }
    """

    # 1. Compute scores
    career_scores = compute_career_scores(db, student_id)
    cluster_scores = compute_cluster_scores(db, career_scores)
    student_keyskills = get_student_keyskill_scores(db, student_id)

    # 2. Fetch DB objects
    clusters = db.query(models.CareerCluster).all()
    careers = db.query(models.Career).all()
    keyskills = {ks.id: ks for ks in db.query(models.KeySkill).all()}

    # 3. Sort for top results
    top_clusters = sorted(cluster_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    top_careers = sorted(career_scores.items(), key=lambda x: x[1], reverse=True)[:5]

    cluster_output = []
    career_output = []

    # ---------------------------
    # CLUSTER EXPLANATIONS
    # ---------------------------
    for cluster_id, score in top_clusters:
        cluster = next((c for c in clusters if c.id == cluster_id), None)
        if not cluster:
            continue

        # student keyskills that belong to this cluster
        contributing = []
        for ks_id, val in student_keyskills.items():
            if val <= 0:
                continue
            ks_obj = keyskills.get(ks_id)
            if not ks_obj:
                continue
            if ks_obj.cluster_id == cluster_id:
                contributing.append(ks_obj)
        contributing = contributing[:3]

        # --- cluster band breakdown (core/supporting/auxiliary) ---
        cluster_careers = [c for c in careers if c.cluster_id == cluster_id]

        band_contrib = {"core": 0.0, "supporting": 0.0, "auxiliary": 0.0}

        for career in cluster_careers:
            ks_rows = db.execute(
                select(
                    models.career_keyskill_association.c.keyskill_id,
                    models.career_keyskill_association.c.weight_percentage,
                ).where(
                    models.career_keyskill_association.c.career_id == career.id
                )
            ).all()

            for ks_id, weight in ks_rows:
                # Only count weights for keyskills the student actually has
                if student_keyskills.get(ks_id, 0) <= 0:
                    continue

                # classify into bands using weightage rationale
                if weight >= 30:
                    band = "core"
                elif weight >= 20:
                    band = "supporting"
                else:
                    band = "auxiliary"

                band_contrib[band] += float(weight)

        total_band = sum(band_contrib.values())
        if total_band > 0:
            band_breakdown = {
                band: round((val / total_band) * 100, 2)
                for band, val in band_contrib.items()
                if val > 0
            }
        else:
            band_breakdown = {}

        cluster_output.append({
            "cluster_id": cluster_id,
            "cluster_name": cluster.name,
            "score": score,
            "top_keyskills": [ks.name for ks in contributing],
            "band_breakdown": band_breakdown,
            "explanation": explain_cluster(cluster, score, contributing, band_breakdown),
        })

    # ---------------------------
    # CAREER EXPLANATIONS
    # ---------------------------
    for career_id, score in top_careers:
        career = next((c for c in careers if c.id == career_id), None)
        if not career:
            continue

        ks_rows = db.execute(
            select(
                models.career_keyskill_association.c.keyskill_id,
                models.career_keyskill_association.c.weight_percentage
            ).where(
                models.career_keyskill_association.c.career_id == career_id
            )
        ).all()

        contributions = []
        for ks_id, weight in ks_rows:
            if student_keyskills.get(ks_id, 0) <= 0:
                continue
            ks_obj = keyskills.get(ks_id)
            if not ks_obj:
                continue
            contributions.append((ks_obj, weight))

        contributions = sorted(contributions, key=lambda x: x[1], reverse=True)[:3]

        career_output.append({
            "career_id": career_id,
            "career_name": career.title,
            "score": score,
            "top_keyskills": [k.name for k, _ in contributions],
            "explanation": explain_career(career, score, [k for k, _ in contributions]),
        })

    return {
        "clusters": cluster_output,
        "careers": career_output,
    }
