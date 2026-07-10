# app/services/notifications/locales.py
#
# Single source of truth for which locales the notification system supports.
# Template lookup, request validation, and fallback logic all import from
# here. Nothing else may hardcode a locale literal (e.g. ["en", "kn"] or
# `if locale == "kn"`) — that is a design failure, not a style nit.
#
# Adding a language: append it to SUPPORTED_LOCALES, add its strings to every
# template in app/services/notifications/templates/, deploy. Nothing else.
#
# These templates are plain Python dicts today. They are expected to move
# into a DB-backed, admin-editable translation store later (mirroring how
# question/AQ translations already work). Keeping every locale reference
# behind this registry is what makes that migration mechanical rather than
# a rewrite: only template lookup needs to change, not every call site.

SUPPORTED_LOCALES = ["en", "kn"]
DEFAULT_LOCALE = "en"


def normalize_locale(locale: str | None) -> str:
    """Lowercases/strips a locale string. Does not validate membership."""
    return (locale or "").strip().lower()


def is_supported_locale(locale: str | None) -> bool:
    return normalize_locale(locale) in SUPPORTED_LOCALES
