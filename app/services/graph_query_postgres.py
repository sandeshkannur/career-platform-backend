# app/services/graph_query_postgres.py
"""
PostgreSQL implementation of GraphQueryInterface.
Uses existing tables: aq_student_skill_weight, student_skill_scores,
career_student_skill, careers, career_clusters, associated_qualities.

When migrating to Neo4j: create graph_query_neo4j.py implementing the same
interface, swap the import in graph_query_service.py. Done.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.services.graph_query_interface import GraphQueryInterface

# AQ code → display name mapping (from live DB associated_qualities table)
# Cached here to avoid repeated DB lookups
AQ_NAMES = {
    "AQ_01": "Curiosity Drive", "AQ_02": "Inquiry Framing",
    "AQ_03": "Numerical Reasoning", "AQ_04": "Systems Analysis",
    "AQ_05": "Logical Deduction", "AQ_06": "Information Synthesis",
    "AQ_07": "Spatial Reasoning", "AQ_08": "Abstract Creativity",
    "AQ_09": "Idea Generation", "AQ_10": "Experimentation Mindset",
    "AQ_11": "Applied Solutioning", "AQ_12": "Attention Regulation",
    "AQ_13": "Precision & Accuracy", "AQ_14": "Planning & Prioritization",
    "AQ_15": "Goal Commitment", "AQ_16": "Persistence & Grit",
    "AQ_17": "Self-Discipline", "AQ_18": "Adaptive Flexibility",
    "AQ_19": "Feedback Openness", "AQ_20": "Emotional Insight",
    "AQ_21": "Stress Tolerance", "AQ_22": "Perspective Taking",
    "AQ_23": "Cooperative Responsibility", "AQ_24": "Integrity & Fairness",
    "AQ_25": "Communication Effectiveness",
}

# AQ → student skill mapping (from aq_student_skill_weight table)
# Used for what-if simulation: when AQ improves, which skills improve?
AQ_TO_SKILLS = {
    "AQ_01": ["Curiosity", "Adaptability & Flexibility", "Creativity & Innovation"],
    "AQ_02": ["Critical Thinking & Problem Solving", "Curiosity"],
    "AQ_03": ["Critical Thinking & Problem Solving", "Financial Literacy"],
    "AQ_04": ["Critical Thinking & Problem Solving", "Decision-Making"],
    "AQ_05": ["Critical Thinking & Problem Solving"],
    "AQ_06": ["Critical Thinking & Problem Solving", "Information Literacy"],
    "AQ_07": ["Decision-Making", "Creativity & Innovation"],
    "AQ_08": ["Creativity & Innovation"],
    "AQ_09": ["Creativity & Innovation", "Curiosity"],
    "AQ_10": ["Adaptability & Flexibility", "Creativity & Innovation"],
    "AQ_11": ["Critical Thinking & Problem Solving", "Productivity"],
    "AQ_12": ["Productivity", "Time Management"],
    "AQ_13": ["Information Literacy", "Productivity"],
    "AQ_14": ["Grit & Self-Direction", "Time Management"],
    "AQ_15": ["Grit & Self-Direction", "Ethical Reasoning"],
    "AQ_16": ["Grit & Self-Direction", "Coping with Stress & Resilience"],
    "AQ_17": ["Productivity", "Grit & Self-Direction"],
    "AQ_18": ["Adaptability & Flexibility", "Grit & Self-Direction"],
    "AQ_19": ["Adaptability & Flexibility", "Coping with Stress & Resilience"],
    "AQ_20": ["Coping with Stress & Resilience"],
    "AQ_21": ["Coping with Stress & Resilience"],
    "AQ_22": ["Social & Cross-Cultural Skills", "Collaboration & Teamwork"],
    "AQ_23": ["Collaboration & Teamwork", "Ethical Reasoning"],
    "AQ_24": ["Information Literacy", "Ethical Reasoning"],
    "AQ_25": ["Communication Skills", "Collaboration & Teamwork"],
}

# AQ weight per skill (how much does a 1-point AQ improvement affect the skill)
# Derived from aq_student_skill_weight table weights
AQ_SKILL_WEIGHT = {
    ("AQ_01", "Curiosity"): 0.333,
    ("AQ_01", "Adaptability & Flexibility"): 0.25,
    ("AQ_01", "Creativity & Innovation"): 0.25,
    ("AQ_02", "Critical Thinking & Problem Solving"): 0.2,
    ("AQ_02", "Curiosity"): 0.333,
    ("AQ_25", "Communication Skills"): 0.25,
    ("AQ_25", "Collaboration & Teamwork"): 0.25,
    # Add more as needed — these are the key ones
}


def _fit_band(score: float) -> str:
    if score >= 80:
        return "high_potential"
    if score >= 65:
        return "strong"
    if score >= 50:
        return "promising"
    if score >= 35:
        return "developing"
    return "exploring"


class PostgresGraphQuery(GraphQueryInterface):

    def __init__(self, db: Session):
        self.db = db

    def _get_student_skill_scores(self, student_id: int) -> dict:
        """Returns {skill_name: hsi_score} from most recent assessment that has skill scores."""
        rows = self.db.execute(text("""
            SELECT sk.name AS skill, sss.hsi_score
            FROM student_skill_scores sss
            JOIN skills sk ON sk.id = sss.skill_id
            WHERE sss.student_id = :sid
              AND sss.assessment_id = (
                SELECT assessment_id
                FROM student_skill_scores
                WHERE student_id = :sid
                ORDER BY assessment_id DESC
                LIMIT 1
              )
        """), {"sid": student_id}).fetchall()
        return {r.skill: float(r.hsi_score or 0) for r in rows}

    def _compute_career_scores(self, skill_scores: dict) -> list:
        """
        Computes scores for all careers given a skill score dict.
        Returns list of {id, title, cluster, score} sorted desc.
        """
        rows = self.db.execute(text("""
            SELECT c.id, c.title, cc.name AS cluster,
                   css.student_skill, css.weight
            FROM career_student_skill css
            JOIN careers c ON c.id = css.career_id
            JOIN career_clusters cc ON cc.id = c.cluster_id
            WHERE css.weight > 0
        """)).fetchall()

        career_data = {}
        for r in rows:
            cid = r.id
            if cid not in career_data:
                career_data[cid] = {
                    "id": cid, "title": r.title,
                    "cluster": r.cluster, "score": 0.0,
                }
            skill_score = skill_scores.get(r.student_skill, 0)
            career_data[cid]["score"] += (skill_score * float(r.weight)) / 100.0

        results = list(career_data.values())
        results.sort(key=lambda x: -x["score"])
        return results

    # ------------------------------------------------------------------
    # AQ Influence Map
    # ------------------------------------------------------------------

    def get_aq_influence_map(self, student_id: int) -> dict:
        # Get AQ weights from DB
        aq_rows = self.db.execute(text("""
            SELECT aq_code, student_skill, weight
            FROM aq_student_skill_weight
            ORDER BY aq_code, weight DESC
        """)).fetchall()

        # Get career skill weights
        career_rows = self.db.execute(text("""
            SELECT c.title, cc.name AS cluster,
                   css.student_skill, css.weight
            FROM career_student_skill css
            JOIN careers c ON c.id = css.career_id
            JOIN career_clusters cc ON cc.id = c.cluster_id
            WHERE css.weight > 0
        """)).fetchall()

        # Build AQ → career influence
        # influence = aq_skill_weight × career_skill_weight / 100
        aq_influences = {}
        for aq_row in aq_rows:
            aq = aq_row.aq_code
            skill = aq_row.student_skill
            aq_wt = float(aq_row.weight)

            if aq not in aq_influences:
                aq_influences[aq] = {
                    "aq_code": aq,
                    "aq_name": AQ_NAMES.get(aq, aq),
                    "student_score": 0.0,
                    "career_influence": {},
                    "cluster_influence": {},
                }

            for cr in career_rows:
                if cr.student_skill != skill:
                    continue
                influence = aq_wt * float(cr.weight) / 100.0
                title = cr.title
                cluster = cr.cluster
                aq_influences[aq]["career_influence"][title] = (
                    aq_influences[aq]["career_influence"].get(title, 0) + influence
                )
                aq_influences[aq]["cluster_influence"][cluster] = (
                    aq_influences[aq]["cluster_influence"].get(cluster, 0) + influence
                )

        # Add student scores per AQ (weighted average of skill scores)
        aq_score_rows = self.db.execute(text("""
            SELECT asw.aq_code,
                   AVG(sss.hsi_score * asw.weight) AS weighted_score
            FROM aq_student_skill_weight asw
            JOIN skills sk ON sk.name = asw.student_skill
            JOIN student_skill_scores sss ON sss.skill_id = sk.id
            WHERE sss.student_id = :sid
              AND sss.assessment_id = (
                SELECT a.id FROM assessments a
                WHERE a.user_id = (SELECT user_id FROM students WHERE id = :sid)
                ORDER BY a.submitted_at DESC LIMIT 1
              )
            GROUP BY asw.aq_code
        """), {"sid": student_id}).fetchall()

        for r in aq_score_rows:
            if r.aq_code in aq_influences:
                aq_influences[r.aq_code]["student_score"] = round(
                    float(r.weighted_score or 0), 1
                )

        # Sort and format output
        result_list = []
        for aq, data in sorted(aq_influences.items()):
            top_careers = sorted(
                data["career_influence"].items(), key=lambda x: -x[1]
            )[:5]
            top_clusters = sorted(
                data["cluster_influence"].items(), key=lambda x: -x[1]
            )[:5]
            result_list.append({
                "aq_code": data["aq_code"],
                "aq_name": data["aq_name"],
                "student_score": data["student_score"],
                "top_careers": [
                    {"title": t, "influence_weight": round(w, 3)}
                    for t, w in top_careers
                ],
                "top_clusters": [
                    {"cluster": c, "influence_weight": round(w, 3)}
                    for c, w in top_clusters
                ],
            })

        result_list.sort(key=lambda x: -x["student_score"])
        return {"aq_influences": result_list}

    # ------------------------------------------------------------------
    # What-If Simulation
    # ------------------------------------------------------------------

    def get_whatif_simulation(
        self, student_id: int, aq_code: str, delta: float
    ) -> dict:
        delta = max(-30.0, min(30.0, float(delta)))  # cap delta ±30
        skill_scores = self._get_student_skill_scores(student_id)

        before_careers = self._compute_career_scores(skill_scores)[:9]

        # Apply delta: improve skills fed by this AQ proportionally
        modified_scores = dict(skill_scores)
        aq_rows = self.db.execute(text("""
            SELECT student_skill, weight
            FROM aq_student_skill_weight
            WHERE aq_code = :aq
        """), {"aq": aq_code}).fetchall()

        for r in aq_rows:
            skill = r.student_skill
            skill_delta = delta * float(r.weight)
            if skill in modified_scores:
                modified_scores[skill] = min(100.0, max(0.0,
                    modified_scores[skill] + skill_delta
                ))

        after_careers = self._compute_career_scores(modified_scores)[:9]

        before_set = {c["title"]: i + 1 for i, c in enumerate(before_careers)}
        after_set = {c["title"]: i + 1 for i, c in enumerate(after_careers)}

        entered = [c for c in after_careers if c["title"] not in before_set]
        left = [c for c in before_careers if c["title"] not in after_set]

        rank_changes = []
        for title, after_rank in after_set.items():
            if title in before_set:
                before_rank = before_set[title]
                change = before_rank - after_rank
                if change != 0:
                    rank_changes.append({
                        "title": title,
                        "before_rank": before_rank,
                        "after_rank": after_rank,
                        "change": change,
                    })
        rank_changes.sort(key=lambda x: -abs(x["change"]))

        return {
            "aq_code": aq_code,
            "aq_name": AQ_NAMES.get(aq_code, aq_code),
            "delta": delta,
            "before": [
                {"rank": i + 1, "title": c["title"],
                 "cluster": c["cluster"], "score": round(c["score"], 1)}
                for i, c in enumerate(before_careers)
            ],
            "after": [
                {"rank": i + 1, "title": c["title"],
                 "cluster": c["cluster"], "score": round(c["score"], 1)}
                for i, c in enumerate(after_careers)
            ],
            "entered_top9": [
                {"title": c["title"], "cluster": c["cluster"],
                 "score": round(c["score"], 1)} for c in entered
            ],
            "left_top9": [
                {"title": c["title"], "cluster": c["cluster"],
                 "score": round(c["score"], 1)} for c in left
            ],
            "rank_changes": rank_changes,
        }

    # ------------------------------------------------------------------
    # Cluster Reachability
    # ------------------------------------------------------------------

    def get_cluster_reachability(self, student_id: int) -> dict:
        skill_scores = self._get_student_skill_scores(student_id)
        all_careers = self._compute_career_scores(skill_scores)

        # Group by cluster — take best scoring career per cluster
        clusters = {}
        for c in all_careers:
            cl = c["cluster"]
            if cl not in clusters:
                clusters[cl] = {
                    "cluster": cl,
                    "score": round(c["score"], 1),
                    "top_career": c["title"],
                    "fit_band": _fit_band(c["score"]),
                }

        reachable_now = []
        reachable_with_effort = []
        aspirational = []

        for cl_data in sorted(clusters.values(), key=lambda x: -x["score"]):
            score = cl_data["score"]
            if score >= 50:
                reachable_now.append(cl_data)
            elif score >= 35:
                cl_data["gap"] = round(50.0 - score, 1)
                reachable_with_effort.append(cl_data)
            else:
                cl_data["gap"] = round(50.0 - score, 1)
                aspirational.append(cl_data)

        return {
            "reachable_now": reachable_now,
            "reachable_with_effort": reachable_with_effort,
            "aspirational": aspirational,
        }

    # ------------------------------------------------------------------
    # Career Pathway
    # ------------------------------------------------------------------

    def get_career_pathway(
        self, student_id: int, target_career_title: str
    ) -> dict:
        skill_scores = self._get_student_skill_scores(student_id)

        career_row = self.db.execute(text("""
            SELECT c.id, c.title, cc.name AS cluster
            FROM careers c
            JOIN career_clusters cc ON cc.id = c.cluster_id
            WHERE LOWER(c.title) = LOWER(:title)
            LIMIT 1
        """), {"title": target_career_title}).fetchone()

        if not career_row:
            return {"error": f"Career '{target_career_title}' not found"}

        skill_rows = self.db.execute(text("""
            SELECT css.student_skill, css.weight
            FROM career_student_skill css
            WHERE css.career_id = :cid AND css.weight > 0
            ORDER BY css.weight DESC
        """), {"cid": career_row.id}).fetchall()

        # Compute current score for this career
        current_score = sum(
            skill_scores.get(r.student_skill, 0) * float(r.weight) / 100.0
            for r in skill_rows
        )

        TARGET_BAND_SCORE = 65.0  # "strong" fit band threshold

        # Compute per-skill gaps and driving AQs
        skill_gaps = []
        for r in skill_rows:
            skill = r.student_skill
            weight = float(r.weight)
            current = skill_scores.get(skill, 0)
            # Required improvement in this skill to close the career-level gap
            required = min(
                100.0,
                current + (TARGET_BAND_SCORE - current_score) * (100.0 / weight)
            )
            required = max(current, min(100.0, required))
            gap = max(0.0, required - current)

            # Driving AQs for this skill
            aq_rows = self.db.execute(text("""
                SELECT aq_code, weight
                FROM aq_student_skill_weight
                WHERE student_skill = :skill
                ORDER BY weight DESC
            """), {"skill": skill}).fetchall()

            driving_aqs = [
                {
                    "aq_code": r2.aq_code,
                    "aq_name": AQ_NAMES.get(r2.aq_code, r2.aq_code),
                    "contribution": round(float(r2.weight), 3),
                }
                for r2 in aq_rows
            ]

            skill_gaps.append({
                "skill": skill,
                "current_score": round(current, 1),
                "required_score": round(required, 1),
                "gap": round(gap, 1),
                "career_weight": weight,
                "driving_aqs": driving_aqs,
            })

        # Recommended AQs: highest aggregate impact on gap closure
        aq_impact = {}
        for sg in skill_gaps:
            if sg["gap"] <= 0:
                continue
            for aq in sg["driving_aqs"]:
                code = aq["aq_code"]
                impact = aq["contribution"] * sg["gap"] * sg["career_weight"] / 100.0
                aq_impact[code] = aq_impact.get(code, 0) + impact

        recommended_aqs = sorted(
            [
                {
                    "aq_code": k,
                    "aq_name": AQ_NAMES.get(k, k),
                    "impact_score": round(v, 3),
                }
                for k, v in aq_impact.items()
            ],
            key=lambda x: -x["impact_score"],
        )[:5]

        return {
            "target_career": career_row.title,
            "target_cluster": career_row.cluster,
            "current_score": round(current_score, 1),
            "target_score": TARGET_BAND_SCORE,
            "gap": round(max(0.0, TARGET_BAND_SCORE - current_score), 1),
            "reachable": current_score >= TARGET_BAND_SCORE,
            "skill_gaps": [sg for sg in skill_gaps if sg["gap"] > 0][:8],
            "recommended_focus_aqs": recommended_aqs,
        }
