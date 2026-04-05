"""
app/services/cluster_reranker.py

Pure function — no DB access, no side effects.
Reorders a score-sorted career list to guarantee cluster diversity in the
top results, then fills remaining slots in score order.
"""


def spread_and_select(
    ranked_careers: list[dict],
    num_clusters_in_first_pass: int = 5,
    total_results: int = 10,
) -> list[dict]:
    """
    Two-pass cluster diversity reranker.

    PASS 1 — Cluster spread:
      Iterate ranked_careers (score descending). Add the first career seen
      from each cluster until num_clusters_in_first_pass unique clusters are
      represented, or the list is exhausted.

    PASS 2 — Fill remaining slots:
      Continue through the remainder (skipping already-added careers) in score
      order until total_results is reached.

    Score values are never modified — only ordering changes.
    If len(ranked_careers) < total_results, all careers are returned.
    """
    if not ranked_careers:
        return []

    seen_ids: set[int] = set()
    pass1: list[dict] = []
    seen_clusters: set = set()

    for career in ranked_careers:
        if len(pass1) >= num_clusters_in_first_pass:
            break
        cluster_id = career.get("cluster_id")
        if cluster_id not in seen_clusters:
            pass1.append(career)
            seen_ids.add(career["career_id"])
            seen_clusters.add(cluster_id)

    # Pass 2 — fill remaining slots in original score order
    pass2: list[dict] = []
    for career in ranked_careers:
        if len(pass1) + len(pass2) >= total_results:
            break
        if career["career_id"] not in seen_ids:
            pass2.append(career)

    return pass1 + pass2


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
