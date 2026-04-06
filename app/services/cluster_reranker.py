"""
app/services/cluster_reranker.py

Pure function — no DB access, no side effects.
Reorders a score-sorted career list to guarantee cluster diversity in the
top results, then fills remaining slots in score order.
"""


def spread_and_select(
    scored_careers: list[dict],
    total_results: int,
    num_clusters_in_first_pass: int | None = None,
) -> list[dict]:
    """
    Reorders a score-sorted career list to guarantee cluster diversity
    WITHOUT pulling low-scoring careers just to fill cluster slots.

    Strategy:
    - Only diversify across careers within 30 points of the top score
    - Careers more than 30 points below top are never promoted for diversity
    - After first-pass cluster selection, fill remaining slots in pure score order
    """
    if not scored_careers:
        return []

    total_results = min(total_results, len(scored_careers))
    if total_results == 0:
        return []

    sorted_careers = sorted(
        scored_careers, key=lambda x: x.get("score", 0), reverse=True
    )

    if total_results <= 1:
        return sorted_careers[:total_results]

    top_score = sorted_careers[0].get("score", 0)
    DIVERSITY_THRESHOLD = 30  # only diversify within 30 pts of top score

    seen_clusters = set()
    first_pass = []
    remainder = []

    for c in sorted_careers:
        cluster = c.get("cluster") or c.get("cluster_title") or "Unknown"
        score = c.get("score", 0)
        in_threshold = (top_score - score) <= DIVERSITY_THRESHOLD

        if cluster not in seen_clusters and in_threshold:
            seen_clusters.add(cluster)
            first_pass.append(c)
        else:
            remainder.append(c)

    # Cap first pass to num_clusters_in_first_pass if specified
    if num_clusters_in_first_pass is not None:
        cap = min(num_clusters_in_first_pass, len(first_pass), total_results)
        if len(first_pass) > cap:
            excess = first_pass[cap:]
            first_pass = first_pass[:cap]
            remainder = sorted(
                excess + remainder,
                key=lambda x: x.get("score", 0), reverse=True
            )

    # Fill remaining slots in pure score order
    result = first_pass[:]
    used_ids = {c.get("career_id") or c.get("career_code") for c in result}

    for c in sorted_careers:
        if len(result) >= total_results:
            break
        cid = c.get("career_id") or c.get("career_code")
        if cid not in used_ids:
            result.append(c)
            used_ids.add(cid)

    return result[:total_results]


if __name__ == "__main__":
    # ---------- test data ----------
    mock_careers = [
        {"career_id": 1, "title": "Software Engineer",      "cluster_id": 10, "score": 95.0},
        {"career_id": 2, "title": "Data Scientist",         "cluster_id": 10, "score": 92.0},
        {"career_id": 3, "title": "Product Manager",        "cluster_id": 10, "score": 89.0},
        {"career_id": 4, "title": "Civil Engineer",         "cluster_id": 20, "score": 85.0},
        {"career_id": 5, "title": "Architect",              "cluster_id": 20, "score": 82.0},
        {"career_id": 6, "title": "Doctor",                 "cluster_id": 30, "score": 78.0},
        {"career_id": 7, "title": "Nurse",                  "cluster_id": 30, "score": 74.0},
        {"career_id": 8, "title": "Chartered Accountant",   "cluster_id": 10, "score": 70.0},
        {"career_id": 9, "title": "Investment Banker",      "cluster_id": 10, "score": 68.0},
        {"career_id":10, "title": "Graphic Designer",       "cluster_id": 20, "score": 65.0},
    ]

    print("=== BEFORE (score order) ===")
    for i, c in enumerate(mock_careers, 1):
        print(f"  {i:2}. [{c['cluster_id']}] {c['title']} — score {c['score']}")

    result = spread_and_select(mock_careers, num_clusters_in_first_pass=5, total_results=10)

    print("\n=== AFTER spread_and_select(num_clusters=5, total=10) ===")
    for i, c in enumerate(result, 1):
        print(f"  {i:2}. [{c['cluster_id']}] {c['title']} — score {c['score']}")

    # Assert first 3 results come from 3 different clusters
    first_3_clusters = [c["cluster_id"] for c in result[:3]]
    assert len(set(first_3_clusters)) == 3, (
        f"Expected 3 unique clusters in first 3 results, got: {first_3_clusters}"
    )
    print(f"\nOK: first 3 clusters are {first_3_clusters} (all different)")

    # Assert scores are not modified
    score_map = {c["career_id"]: c["score"] for c in mock_careers}
    for c in result:
        assert c["score"] == score_map[c["career_id"]], "Score was modified!"
    print("OK: scores unchanged")

    print(f"\nOK: total results returned: {len(result)}")
