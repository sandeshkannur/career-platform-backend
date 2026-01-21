import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiGet } from "../../apiClient";
import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";
import { useSession } from "../../hooks/useSession";

export default function StudentResultsHistoryPage() {
  const navigate = useNavigate();
  const { sessionUser } = useSession();

  // Backend-authoritative student identity:
  // Resolve student_id via /v1/students/students/me (NOT via auth/me student_profile).
  const [studentId, setStudentId] = useState(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [items, setItems] = useState([]);

  async function resolveStudentId() {
    // Only attempt after session exists (prevents noisy calls before auth state is ready)
    if (!sessionUser) return;

    try {
      const meStudent = await apiGet(`/v1/students/students/me`);
      setStudentId(meStudent?.id ?? null);
    } catch (e) {
      setStudentId(null);
      setError(e?.message || "Student profile not ready.");
      setLoading(false);
    }
  }

  async function loadHistory() {
    if (!studentId) {
      setError("Student not ready");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError("");

      // openapi shows /v1/students/{id}/assessments
      const res = await apiGet(`/v1/students/${studentId}/assessments`);
      setItems(Array.isArray(res?.assessments) ? res.assessments : []);
    } catch (e) {
      setError(e?.message || "Could not load history.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    resolveStudentId();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionUser]);

  useEffect(() => {
    if (studentId) loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId]);

  return (
    <SkeletonPage title="Results History" subtitle="Previous assessments and recommendations.">
      <div className="flex gap-2 justify-end">
        <Button onClick={() => navigate("/student/results/latest")}>
          Back to Latest
        </Button>
        <Button variant="secondary" disabled>
          Download Report
        </Button>
      </div>

      {loading ? (
        <p>Loading history…</p>
      ) : error ? (
        <div className="card">
          <h3>Student not ready</h3>
          <p>{error}</p>
          <Button onClick={() => {
            setLoading(true);
            setError("");
            resolveStudentId();
          }}>
            Retry
          </Button>
        </div>
      ) : (
        <div className="card">
          {items.length === 0 ? (
            <p>No assessments found yet.</p>
          ) : (
            <div className="space-y-2">
              {items.map((a) => (
                <div key={a.assessment_id} className="card">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="font-semibold">Assessment #{a.assessment_id}</div>
                      <div className="text-sm text-muted">
                        Submitted:{" "}
                        {a.submitted_at ? new Date(a.submitted_at).toLocaleString() : "—"}
                      </div>
                      <div className="text-sm text-muted">
                        Config: {a.scoring_config_version ?? "—"}
                      </div>
                    </div>

                    <Button
                      onClick={() =>
                        navigate(`/student/results/latest?assessmentId=${a.assessment_id}`)
                      }
                    >
                      View
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </SkeletonPage>
  );
}
