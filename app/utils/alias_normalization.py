# app/utils/alias_normalization.py
from __future__ import annotations

import re
from typing import Dict, Optional


def resolve_alias(value: Optional[str], alias_map: Dict[str, str]) -> str:
    """
    Resolve an incoming value to a canonical value using a provided alias map.

    Deterministic normalization rules:
    - None -> ""
    - Trim whitespace
    - Collapse internal whitespace
    - Lowercase for matching
    - If not found in alias_map, return the normalized value

    NOTE: alias_map should be built with normalized keys (lower/trim/collapsed).
    """
    if value is None:
        return ""

    # Normalize user/input string for consistent matching
    v = re.sub(r"\s+", " ", str(value).strip()).lower()
    if not v:
        return ""

    return alias_map.get(v, v)
