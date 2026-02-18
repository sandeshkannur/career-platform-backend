// src/api/assessments.js
// Thin API wrappers for assessment lifecycle.
// Backend behavior is LOCKED. No auth / token logic here.
// apiClient.js handles headers, refresh, and errors.

import { apiGet, apiPost } from "../apiClient";

/**
 * GET /v1/assessments/active
 * Returns active assessment resume state (backend authoritative).
 */
export async function getActiveAssessment() {
  return apiGet("/v1/assessments/active");
}
/**
 * GET /v1/assessments/{assessment_id}/questions
 * Returns canonical question set for the attempt (backend authoritative).
 *
 * Response shape:
 * {
 *   assessment_version,
 *   lang,
 *   lang_used,
 *   count_returned,
 *   questions: [{ question_id, question_code, skill_id, question_text, facet_tags }]
 * }
 */
export async function getAssessmentQuestions(assessmentId, lang) {
  if (!assessmentId) throw new Error("assessmentId is required");

  const qs = lang ? `?lang=${encodeURIComponent(lang)}` : "";
  return apiGet(`/v1/assessments/${assessmentId}/questions${qs}`);
}
/**
 * POST /v1/assessments/
 * Creates a new assessment run for the current user.
 *
 * Returns:
 * { id, user_id, submitted_at, ... }   (whatever your backend returns)
 *
 * NOTE: Some UI code historically expects `assessment_id`.
 * We normalize by adding `assessment_id` when backend returns `id`.
 */
export async function startAssessment(payload = {}) {
  const res = await apiPost("/v1/assessments/", payload);

  // Normalize response shape for older UI expectations
  if (res && res.id != null && res.assessment_id == null) {
    return { ...res, assessment_id: res.id };
  }
  return res;
}

/**
 * GET /v1/assessments/{assessment_id}
 * Fetches assessment metadata + snapshot for resume flow.
 */
export async function getAssessment(assessmentId) {
  if (!assessmentId) throw new Error("assessmentId is required");
  return apiGet(`/v1/assessments/${assessmentId}`);
}

/**
 * POST /v1/assessments/{assessment_id}/submit-assessment
 * Submits completed responses for scoring.
 */
export async function submitAssessment(assessmentId, payload = {}) {
  if (!assessmentId) throw new Error("assessmentId is required");
  return apiPost(`/v1/assessments/${assessmentId}/submit-assessment`, payload);
}
/**
 * POST /v1/assessments/{assessment_id}/responses
 * Submits one or more immutable responses (backend authoritative + idempotent).
 *
 * Payload shape (array):
 * [
 *   { question_id: "12", answer: "5", idempotency_key: "..." },
 *   ...
 * ]
 */
export async function postAssessmentResponses(assessmentId, responses = []) {
  if (!assessmentId) throw new Error("assessmentId is required");
  return apiPost(`/v1/assessments/${assessmentId}/responses`, responses);
}
