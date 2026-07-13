# app/services/notifications/sms_base.py
#
# SmsNotifier contract. Every implementation (log, future real gateway) must
# satisfy this Protocol.
#
# HARD RULE: an SmsNotifier must never raise. Delivery is best-effort from the
# caller's point of view — the calling request (e.g. POST
# /v1/auth/forgot-password/request) must succeed or fail on its own merits,
# never because an SMS gateway had a bad day. Implementations must catch
# their own exceptions, log loudly, and return.

from __future__ import annotations

from typing import Protocol


class SmsNotifier(Protocol):
    def send(self, to_number: str, message: str) -> None:
        """
        Delivers `message` to `to_number`.

        Must never raise. On any failure (provider error, network issue),
        log the failure and return.
        """
        ...
