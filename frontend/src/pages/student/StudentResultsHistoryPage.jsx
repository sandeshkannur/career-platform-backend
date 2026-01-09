// src/pages/student/StudentResultsHistoryPage.jsx
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";
import { useSession } from "../../hooks/useSession";
import { getStudentAssessments } from "../../api/students";

function formatDate(value) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

export default function StudentResultsHistoryPage() {
  const navigate = useNavigate();
  const { sessionUser } = useSession();

  // Match StudentDashboardPage + StudentResultsPage: stable studentId source of truth.
  const studentId = useMemo(() => {
    return sessionUser?.student_profile?.student_id ?? null;
  }, [sessionUser]);

  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState(null);

  // Special states
  const [notReady, setNotReady] = useState(false); // 404 => no history yet

  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!studentId) return;

      setLoading(true);
      setHistory(null);
      setNotReady(false);
      setError(null);

      try {
        const data = await getStudentAssessments(studentId);
        if (cancelled) return;
        setHistory(data);
      } catch (e) {
        if (cancelled) return;

        const status = e?.status || e?.response?.status;

        // Backend currently uses 404 for "no assessments yet"
        if (status === 404) {
          setNotReady(true);
          return;
        }

        const message =
          e?.message ||
          e?.detail ||
          e?.response?.data?.detail ||
          "Failed to load assessment history.";

        setError({ status, message, raw: e });
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [studentId]);

  const showEmpty =
    !studentId ||
    notReady ||
    (history && Array.isArray(history.assessments) && history.assessments.length === 0);

  const items = Array.isArray(history?.assessments) ? history.assessments : [];

  return (
    <SkeletonPage
      title="Results History"
      subtitle="Previous assessments and recommendations."
      actions={
        <>
          <Button
            variant="secondary"
            onClick={() => navigate("/student/results/latest")}
          >
            Back to Latest
          </Button>

          <Button
            disabled={!studentId}
            title={!studentId ? "Student id not available in session yet" : ""}
            onClick={() => {
              if (!studentId) return;
              navigate(`/student/reports/${studentId}`);
            }}
          >
            Download Report
          </Button>
        </>
      }
      empty={showEmpty}
      emptyTitle={!studentId ? "Student not ready" : "No past results"}
      emptyDescription={
        !studentId
          ? "Could not determine student id from session. Please re-login."
          : "Once you submit assessments, your previous attempts will appear here."
      }
    >
      {studentId && loading && (
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          Loading history…
        </div>
      )}

      {studentId && error && !loading && (
        <div
          style={{
            padding: 12,
            border: "1px solid #f3b4b4",
            background: "#fff6f6",
            borderRadius: 8,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 6 }}>
            Failed to load history{error.status ? ` (HTTP ${error.status})` : ""}
          </div>
          <div style={{ fontSize: 14 }}>{error.message}</div>
          <div style={{ marginTop: 10 }}>
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </div>
        </div>
      )}

      {studentId && history && !loading && !showEmpty && (
        <div style={{ display: "grid", gap: 10 }}>
          <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>
              Attempts ({history.total_assessments})
            </div>
            {history.message ? (
              <div style={{ fontSize: 13, opacity: 0.85 }}>{history.message}</div>
            ) : null}
          </div>

          {items.map((it, idx) => {
            // We don't assume exact item fields beyond "submitted_at" existing per endpoint contract.
            const submittedAt = formatDate(it?.submitted_at);
            const status = it?.status || it?.state || null;
            const assessmentId = it?.assessment_id ?? it?.id ?? null;

            return (
              <div
                key={assessmentId ?? `${idx}`}
                style={{
                  padding: 12,
                  border: "1px solid #ddd",
                  borderRadius: 8,
                }}
              >
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                  <div style={{ fontWeight: 700 }}>
                    Attempt {idx + 1}
                    {assessmentId != null ? ` · #${assessmentId}` : ""}
                  </div>

                  {status ? (
                    <div style={{ fontSize: 13, opacity: 0.85 }}>
                      Status: {String(status)}
                    </div>
                  ) : null}

                  {submittedAt ? (
                    <div style={{ fontSize: 13, opacity: 0.85 }}>
                      Submitted: {submittedAt}
                    </div>
                  ) : null}
                </div>

                {/* Temporary: raw item preview for schema validation */}
                <pre style={{ margin: "10px 0 0", padding: 10, overflowX: "auto" }}>
                  {JSON.stringify(it, null, 2)}
                </pre>
              </div>
            );
          })}
        </div>
      )}
    </SkeletonPage>
  );
}
