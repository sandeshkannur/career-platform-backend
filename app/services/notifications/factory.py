# app/services/notifications/factory.py
#
# Single entry point for getting a Notifier. CP_NOTIFIER selects the
# implementation; unset or unrecognised values default to "log" so a
# production instance without the variable set behaves exactly as it did
# before this feature existed (prints/logs, sends nothing).

from __future__ import annotations

import logging
import os

from app.services.notifications.base import Notifier
from app.services.notifications.log_notifier import LogNotifier

logger = logging.getLogger(__name__)


def _notifier_name() -> str:
    return (os.getenv("CP_NOTIFIER") or "log").strip().lower()


def get_notifier() -> Notifier:
    name = _notifier_name()

    if name == "ses":
        from app.services.notifications.ses_notifier import SesEmailNotifier

        return SesEmailNotifier()

    if name != "log":
        logger.warning(
            "CP_NOTIFIER=%r is not recognised — falling back to the log notifier "
            "(no email will actually be sent).",
            name,
        )

    return LogNotifier()


def warn_active_notifier_at_startup() -> None:
    """
    Call once at application startup so the active notifier is never
    ambiguous in production logs.
    """
    name = _notifier_name()
    logger.warning("Active notification channel: CP_NOTIFIER=%r", name)
