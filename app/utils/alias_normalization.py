from __future__ import annotations

import re
from typing import Dict, Optional, Tuple, Any


def _normalize(value: Optional[str]) -> str:
    if value is None:
        return ""
    v = re.sub(r"\s+", " ", str(value).strip()).lower()
    return v


def resolve_alias(*args: Any, **kwargs: Any):
    """
    Backward-compatible alias resolver.

    Supports both forms:

    1) Old form:
       resolve_alias(value, alias_map) -> str

    2) New form used by admin upload routes:
       resolve_alias(
           db=db,
           entity_type="AQ" | "FACET" | ...,
           raw_value="...",
           assessment_version="v1",
       ) -> tuple[str, bool]

    Current minimal behavior for the new form:
    - normalize the incoming value
    - return (normalized_value, False)

    This safely unblocks uploads when CSV values are already canonical.
    """
    # Newer keyword-based form used by admin router
    if "raw_value" in kwargs:
        raw_value = kwargs.get("raw_value")
        normalized = _normalize(raw_value)
        return normalized, False

    # Older positional form
    if len(args) == 2:
        value, alias_map = args
        normalized = _normalize(value)
        if not normalized:
            return ""
        return alias_map.get(normalized, normalized)

    raise TypeError("Unsupported resolve_alias() call signature")

    