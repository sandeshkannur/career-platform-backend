import re


def norm(s: str) -> str:
    """
    Normalize strings for matching.
    - Lowercase
    - Trim
    - Collapse whitespace
    - Remove common punctuation noise
    """
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[’']", "", s)        # unify apostrophes
    s = re.sub(r"[^a-z0-9 &/+-]", "", s)  # keep a conservative set
    s = re.sub(r"\s+", " ", s).strip()
    return s
