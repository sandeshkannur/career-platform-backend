# app/services/notifications/base.py
#
# Notifier contract. Every implementation (log, ses, future sms/...) must
# satisfy this Protocol.
#
# HARD RULE: a Notifier must never raise. Delivery is best-effort from the
# caller's point of view — the calling request (e.g. POST /v1/consent/request)
# must succeed or fail on its own merits, never because an email provider had
# a bad day. Implementations must catch their own exceptions, log loudly, and
# return.

from __future__ import annotations

from typing import Protocol


class Notifier(Protocol):
    def send(self, to: str, template: str, context: dict, locale: str) -> None:
        """
        Renders `template` for `locale` with `context` and delivers it to `to`.

        Must never raise. On any failure (bad template, provider error,
        network issue), log the failure and return.
        """
        ...
