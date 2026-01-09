// src/pages/student/StudentResultsPage.jsx
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";
import { useSession } from "../../hooks/useSession";
import { getStudentResults } from "../../api/students";

export default function StudentResultsPage() {
  const navigate = useNavigate();
  const { sessionUser } = useSession();

  // Match StudentDashboardPage: stable studentId source of truth.
  const studentId = useMemo(() => {
    return sessionUser?.student_profile?.student_id ?? null;
  }, [sessionUser]);

  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);

  // Special states
  const [notReady, setNotReady] = useState(false); // 404

  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!studentId) return;

      setLoading(true);
      setResults(null);
      setNotReady(false);
      setError(null);

      try {
        const data = await getStudentResults(studentId);
        if (cancelled) return;
        setResults(data);
      } catch (e) {
        if (cancelled) return;

        const status = e?.status || e?.response?.status;

        if (status === 404) {
          setNotReady(true);
          return;
        }

        const message =
          e?.message ||
          e?.detail ||
          e?.response?.data?.detail ||
          "Failed to load results.";

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

  const showEmpty = !studentId || notReady;

  return (
    <SkeletonPage
      title="Your Career Results"
      subtitle="Top recommendations based on your assessment."
      actions={
        <>
          <Button
            variant="secondary"
            onClick={() => navigate("/student/results/history")}
          >
            View History
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
      emptyTitle="Results not ready"
      emptyDescription={
        !studentId
          ? "Could not determine student id from session. Please re-login."
          : "Complete the assessment (or refresh after scoring completes) to view results."
      }
    >
      {studentId && loading && (
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          Loading results…
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
            Failed to load results{error.status ? ` (HTTP ${error.status})` : ""}
          </div>
          <div style={{ fontSize: 14 }}>{error.message}</div>
          <div style={{ marginTop: 10 }}>
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </div>
        </div>
      )}

      {studentId && results && !loading && (
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <div style={{ fontWeight: 700, marginBottom: 8 }}>
            Results JSON (temporary preview)
          </div>
          <pre style={{ margin: 0, padding: 10, overflowX: "auto" }}>
            {JSON.stringify(results, null, 2)}
          </pre>
        </div>
      )}
    </SkeletonPage>
  );
}
