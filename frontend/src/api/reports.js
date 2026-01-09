// src/api/reports.js
// Thin API wrappers for report endpoints.
// Keep deterministic: return backend payload as-is (no UI shaping here).

import { apiGet } from "../apiClient";

/**
 * GET /v1/reports/{student_id}
 * Fetches the student's generated report JSON.
 *
 * NOTE:
 * - Backend may return 404 if report is not ready yet.
 * - UI will handle that later (Step: UX polish).
 */
export async function getStudentReport(studentId) {
  if (!studentId) throw new Error("studentId is required");
  return apiGet(`/v1/reports/${studentId}`);
}
