import re

_NUM_PATTERNS = [
    re.compile(r"\(\s*\d+\s*/\s*\d+\s*\)"),  # (35/100)
    re.compile(r"\(\s*\d+\s*%\s*\)"),        # (35%)
    re.compile(r"\b\d+\s*/\s*\d+\b"),        # 35/100
    re.compile(r"\b\d+\s*%\b"),              # 35%
]

def _strip_numbers(text: str) -> str:
    t = text
    for rx in _NUM_PATTERNS:
        t = rx.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip()

def sanitize_student_result_payload(payload: dict) -> dict:
    """
    Remove ALL numeric scoring info for student/parent views.
    Keeps structure identical so UI doesn't break.
    """
    out = dict(payload)
    
    # PR44: Never leak internal contribution trace to students
    out.pop("contrib_trace", None)

    results = out.get("results") or []
    for r in results:
        careers = r.get("recommendations") or r.get("top_careers") or []

        for c in careers:
            # Remove numeric fields if present
            for key in [
                "score",
                "score_total",
                "score_norm",
                "driverScore",
                "contribution",
                "percent_contribution",
            ]:
                c.pop(key, None)

            # Clean CMS explainability strings (remove 35%, 35/100, etc.)
            if isinstance(c.get("explainability"), list):
                c["explainability"] = [
                    _strip_numbers(x) if isinstance(x, str) else x
                    for x in c["explainability"]
                ]

    out["results"] = results
    return out
