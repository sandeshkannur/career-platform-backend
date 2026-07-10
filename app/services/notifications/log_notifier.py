# app/services/notifications/log_notifier.py
#
# Default notifier. Logs the rendered subject + body at INFO instead of
# sending anything. This is what CP_NOTIFIER defaults to, so a missing/
# unrecognised configuration degrades to today's behaviour (print-to-stdout)
# rather than silently dropping mail — it's just a logger now, not a print().

from __future__ import annotations

import logging

from app.services.notifications.templates import render

logger = logging.getLogger(__name__)


class LogNotifier:
    def send(self, to: str, template: str, context: dict, locale: str) -> None:
        try:
            message = render(template, locale, context)
        except Exception:
            logger.exception(
                "LogNotifier: failed to render template=%s locale=%s — notification dropped",
                template,
                locale,
            )
            return

        logger.info(
            "LogNotifier: would send to=%s template=%s locale=%s subject=%r\n%s",
            to,
            template,
            locale,
            message.subject,
            message.text,
        )
