// src/api/consent.js
// Thin API wrappers for the Guardian Consent flow.
// Backend behavior is LOCKED. Do not add token logic here.
// apiClient.js (apiGet/apiPost) is the single place that should handle auth headers.

import { apiGet, apiPost } from "../apiClient";

/**
 * POST /v1/consent/request  (student-only)
 * Student initiates guardian consent request.
 *
 * Typical payload (optional depending on backend rules):
 * { guardian_email: "guardian@example.com" }
 *
 * Backend may derive guardian_email from /auth/me or stored profile,
 * so we keep payload flexible.
 *
 * Returns:
 * { consent_id, delivery, expires_at, dev?: { token, otp } }
 */
export async function requestConsent(payload = {}) {
  return apiPost("/v1/consent/request", payload);
}

/**
 * GET /v1/consent/status (student-only)
 * Student checks derived status from consent_logs.
 *
 * Returns a derived state like:
 * { status: "idle" | "sent" | "verified" | "expired", ... }
 */
export async function getConsentStatus() {
  return apiGet("/v1/consent/status");
}

/**
 * POST /v1/consent/verify (guardian-facing, public)
 * Guardian verifies OTP + token.
 *
 * IMPORTANT:
 * - This is a PUBLIC endpoint: no guardian login required.
 * - Payload must include { token, otp } exactly.
 *
 * Returns verification metadata:
 * { verified, status, student_id, guardian_email, verified_at, expires_at, ... }
 */
export async function verifyConsent(payload) {
  if (!payload?.token) throw new Error("token is required");
  if (!payload?.otp) throw new Error("otp is required");
  return apiPost("/v1/consent/verify", payload);
}
