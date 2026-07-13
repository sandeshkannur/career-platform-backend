# app/services/notifications/log_sms_notifier.py
#
# Default (and, for now, only) SMS notifier. Logs the message at INFO
# instead of sending anything. This is what CP_SMS_NOTIFIER defaults to.
#
# TODO(sms-gateway): once TRAI DLT registration is complete, add a real
# implementation (e.g. TraiSmsNotifier) in this package and wire it up in
# get_sms_notifier() below, the same way SesEmailNotifier plugs in next to
# LogNotifier for email.

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class LogSmsNotifier:
    def send(self, to_number: str, message: str) -> None:
        logger.info(
            "LogSmsNotifier: would send to=%s message=%r",
            to_number,
            message,
        )
