from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class OtpRequestIn(BaseModel):
    phone_number: str


class OtpRequestOut(BaseModel):
    expires_at: datetime
    dev: Optional[dict] = None


class OtpVerifyIn(BaseModel):
    phone_number: str
    otp: str
