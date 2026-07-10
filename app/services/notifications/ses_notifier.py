# app/services/notifications/ses_notifier.py
#
# SES-backed email notifier. Sends both text/plain and text/html parts.
#
# HARD RULE (inherited from base.Notifier): send() must never raise. Any
# boto3/ClientError/network failure is caught, logged loudly, and swallowed —
# the calling request (e.g. guardian consent) must succeed regardless of
# whether the email actually left the building.

from __future__ import annotations

import logging
import os

import boto3
from botocore.exceptions import ClientError

from app.services.notifications.templates import render

logger = logging.getLogger(__name__)

DEFAULT_SES_REGION = "ap-south-1"
DEFAULT_SES_FROM_ADDRESS = "support@mapyourcareer.in"


class SesEmailNotifier:
    def __init__(self) -> None:
        self.region = os.getenv("CP_SES_REGION", DEFAULT_SES_REGION)
        self.from_address = os.getenv("CP_SES_FROM_ADDRESS", DEFAULT_SES_FROM_ADDRESS)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("ses", region_name=self.region)
        return self._client

    def send(self, to: str, template: str, context: dict, locale: str) -> None:
        try:
            message = render(template, locale, context)
        except Exception:
            logger.exception(
                "SesEmailNotifier: failed to render template=%s locale=%s — notification dropped",
                template,
                locale,
            )
            return

        try:
            self.client.send_email(
                Source=self.from_address,
                Destination={"ToAddresses": [to]},
                Message={
                    "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": message.text, "Charset": "UTF-8"},
                        "Html": {"Data": message.html, "Charset": "UTF-8"},
                    },
                },
            )
            logger.info(
                "SesEmailNotifier: sent to=%s template=%s locale=%s",
                to,
                template,
                locale,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.error(
                "SesEmailNotifier: SES rejected send to=%s template=%s locale=%s "
                "code=%s message=%s",
                to,
                template,
                locale,
                error_code,
                error_message,
            )
        except Exception:
            logger.exception(
                "SesEmailNotifier: unexpected failure sending to=%s template=%s locale=%s",
                to,
                template,
                locale,
            )
