# app/services/notifications/templates/__init__.py
#
# Template registry + rendering. Each template module (consent_request.py,
# password_reset.py) stores ONLY a subject + plain-text body per locale, as
# Python dicts keyed by locale code. The minimal HTML body is derived here,
# programmatically, from that same reviewed text — so the HTML can never
# drift from the copy that was actually reviewed/approved. No images, no
# external CSS, no tracking pixels; just escaped paragraphs and auto-linked
# URLs, which is what rural Android mail clients render reliably.
#
# Locale membership is NOT decided here — see app/services/notifications/locales.py.
# This module only asks "does this template have this locale's strings?" and
# falls back to DEFAULT_LOCALE (with a loud warning) if not.

from __future__ import annotations

import html as html_escape
import logging
import re
from dataclasses import dataclass
from typing import Dict

from app.services.notifications.locales import DEFAULT_LOCALE, normalize_locale
from app.services.notifications.templates.consent_request import CONSENT_REQUEST_TEMPLATES
from app.services.notifications.templates.password_reset import PASSWORD_RESET_TEMPLATES

logger = logging.getLogger(__name__)

# template_name -> locale -> {"subject": str, "text": str}
TEMPLATES: Dict[str, Dict[str, Dict[str, str]]] = {
    "consent_request": CONSENT_REQUEST_TEMPLATES,
    "password_reset": PASSWORD_RESET_TEMPLATES,
}

_URL_RE = re.compile(r"(https?://\S+)")


@dataclass(frozen=True)
class RenderedMessage:
    subject: str
    text: str
    html: str


def _text_to_minimal_html(text: str) -> str:
    """
    Escapes the text, splits on blank lines into paragraphs, turns single
    newlines into <br>, and auto-links bare URLs. No images, no external
    CSS/JS, no tracking pixels.
    """
    escaped = html_escape.escape(text)
    escaped = _URL_RE.sub(r'<a href="\1">\1</a>', escaped)

    paragraphs = [p.strip() for p in escaped.split("\n\n") if p.strip()]
    body = "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)

    return (
        '<div style="font-family: Arial, Helvetica, sans-serif; '
        'font-size: 15px; line-height: 1.5; color: #111;">'
        f"{body}"
        "</div>"
    )


def render(template_name: str, locale: str, context: dict) -> RenderedMessage:
    """
    Raises ValueError/KeyError for programmer error (unknown template name,
    bad context keys) — callers (Notifier implementations) are responsible
    for catching and logging, per the "never raise" contract on send().
    """
    by_locale = TEMPLATES.get(template_name)
    if by_locale is None:
        raise ValueError(f"Unknown notification template: {template_name!r}")

    requested = normalize_locale(locale)
    strings = by_locale.get(requested)

    if strings is None:
        logger.warning(
            "Notification template missing locale: template=%s locale=%s — "
            "falling back to %s",
            template_name,
            requested,
            DEFAULT_LOCALE,
        )
        strings = by_locale.get(DEFAULT_LOCALE)

    if strings is None:
        # Only reachable if a template forgot to define DEFAULT_LOCALE at all.
        raise ValueError(
            f"Template {template_name!r} has no strings for default locale {DEFAULT_LOCALE!r}"
        )

    subject = strings["subject"].format(**context)
    text = strings["text"].format(**context)
    html = _text_to_minimal_html(text)

    if not text.strip():
        raise ValueError(f"Template {template_name!r}/{requested!r} rendered an empty body")

    return RenderedMessage(subject=subject, text=text, html=html)
