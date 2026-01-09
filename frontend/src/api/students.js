// src/api/students.js
// Thin API wrappers for student endpoints.
// No auth / token logic here (apiClient is responsible).

import { apiGet } from "../apiClient";

/**
 * GET /v1/students/{id}/dashboard
 * Returns dashboard data for a student (owner/admin depending on backend rules).
 */
export async function getStudentDashboard(studentId) {
  if (!studentId) throw new Error("studentId is required");
  return apiGet(`/v1/students/${studentId}/dashboard`);
}

/**
 * GET /v1/students/{id}/assessments
 * Returns assessment attempts / metadata for a student.
 */
export async function getStudentAssessments(studentId) {
  if (!studentId) throw new Error("studentId is required");
  return apiGet(`/v1/students/${studentId}/assessments`);
}

/**
 * GET /v1/students/{id}/results
 * Returns assessment results for a student (if available).
 */
export async function getStudentResults(studentId) {
  if (!studentId) throw new Error("studentId is required");
  return apiGet(`/v1/students/${studentId}/results`);
}
