"""
app/schemas package

Goal (PR-CLEAN-02):
- Make `app.schemas` a PACKAGE (single source of truth).
- Keep backwards compatibility for old imports:
    from app.schemas import <SchemaName>
- Gradually migrate schemas into domain modules under app/schemas/
  without breaking existing code.
"""

from __future__ import annotations

# -------------------------------------------------------------------
# Back-compat shim:
# Re-export everything that used to live in app/schemas.py
# (now renamed to app/schemas_legacy.py)
# -------------------------------------------------------------------
from app.schemas_legacy import *  # noqa: F401,F403


# -------------------------------------------------------------------
# Optional: If you already have domain schema modules under app/schemas/,
# you can also explicitly re-export from them here.
# Only do this if you WANT their names available at `from app.schemas import X`.
# These imports are safe if the files exist.
# -------------------------------------------------------------------
try:
    from .admin_ingest import *  # noqa: F401,F403
except Exception:
    pass

try:
    from .questions import *  # noqa: F401,F403
except Exception:
    pass

try:
    from .questions_random_schemas import *  # noqa: F401,F403
except Exception:
    pass

try:
    from .questions_student import *  # noqa: F401,F403
except Exception:
    pass