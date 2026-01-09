// src/pages/StudentDashboardPage.jsx
import { Link, useNavigate } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";

import SkeletonPage from "../ui/SkeletonPage";
import Button from "../ui/Button";
import { useSession } from "../hooks/useSession";

import {
  getStudentDashboard,
  getStudentAssessments,
  getStudentResults,
} from "../api/students";

export default function StudentDashboardPage() {
  const navigate = useNavigate();
  const { logout, sessionUser } = useSession();

  // IMPORTANT: We need a stable studentId. Adjust only if your /v1/auth/me payload uses a different field.
  const studentId = useMemo(() => {
    // /v1/auth/me => student_profile.student_id is the real studentId for /v1/students/{id}/*
    return sessionUser?.student_profile?.student_id ?? null;
  }, [sessionUser]);

  // Step 1: Read-only consent indicator (no routing logic, no buttons)
  const isStudent = sessionUser?.role === "student";
  const isMinor = sessionUser?.is_minor === true;

  const showConsentVerified =
    isStudent && isMinor && sessionUser?.consent_verified === true;

  const showConsentRequired =
    isStudent && isMinor && sessionUser?.consent_verified !== true;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [dashboard, setDashboard] = useState(null);
  const [assessments, setAssessments] = useState(null);
  const [results, setResults] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!studentId) return;

      setLoading(true);
      setError(null);

      try {
        // Keep ordering deterministic: request all in parallel, but assign results explicitly.
        const [d, a, r] = await Promise.all([
          getStudentDashboard(studentId),
          getStudentAssessments(studentId),
          getStudentResults(studentId),
        ]);

        if (cancelled) return;

        setDashboard(d);
        setAssessments(a);
        setResults(r);
      } catch (e) {
        if (cancelled) return;

        // Normalize a readable error message without changing apiClient behavior
        const status = e?.status || e?.response?.status;
        const message =
          e?.message ||
          e?.detail ||
          e?.response?.data?.detail ||
          "Failed to load dashboard data.";

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

  return (
    <SkeletonPage
      title="Student Dashboard"
      subtitle={
        sessionUser?.full_name
          ? `Welcome, ${sessionUser.full_name}. Choose what you want to do next.`
          : "Choose what you want to do next."
      }
      actions={<Button onClick={logout}>Logout</Button>}
    >
      {/* Step 1: Consent Required Indicator (READ-ONLY) */}
      {showConsentRequired && (
        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              padding: 12,
              border: "1px solid #f0c36d",
              background: "#fff9ef",
              borderRadius: 8,
            }}
          >
            <div style={{ fontWeight: 700 }}>Guardian consent required ⚠️</div>
            <div style={{ fontSize: 13, marginTop: 4, opacity: 0.9 }}>
              Your account is marked as a minor. Please complete guardian consent
              verification to unlock reports and continue.
            </div>
          </div>
        </div>
      )}

      {/* Step 1: Consent Verified Indicator (READ-ONLY) */}
      {showConsentVerified && (
        <div style={{ marginBottom: 16 }}>
          <div
            style={{
              padding: 12,
              border: "1px solid #cfe9d6",
              background: "#f3fff6",
              borderRadius: 8,
            }}
          >
            <div style={{ fontWeight: 700 }}>Parental consent verified ✅</div>
            <div style={{ fontSize: 13, marginTop: 4, opacity: 0.9 }}>
              Your guardian consent is verified. You can continue using the platform.
            </div>
          </div>
        </div>
      )}

      {/* Read-only data section (temporary but extremely useful for schema validation) */}
      <div style={{ marginBottom: 16 }}>
        {!studentId && (
          <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>Session</div>
            <div style={{ fontSize: 14 }}>
              Could not determine <code>studentId</code> from <code>sessionUser</code>.
              <br />
              Please share your <code>/v1/auth/me</code> payload field name for the student id.
            </div>
          </div>
        )}

        {studentId && loading && (
          <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
            Loading dashboard data…
          </div>
        )}

        {studentId && error && (
          <div
            style={{
              padding: 12,
              border: "1px solid #f3b4b4",
              background: "#fff6f6",
              borderRadius: 8,
            }}
          >
            <div style={{ fontWeight: 700, marginBottom: 6 }}>
              Failed to load dashboard data{error.status ? ` (HTTP ${error.status})` : ""}
            </div>
            <div style={{ fontSize: 14 }}>{error.message}</div>
            <div style={{ marginTop: 10 }}>
              <Button variant="secondary" onClick={() => window.location.reload()}>
                Retry
              </Button>
            </div>
          </div>
        )}

        {studentId && !loading && !error && (dashboard || assessments || results) && (
          <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>
              Backend Data (temporary debug view)
            </div>

            <div style={{ display: "grid", gap: 10 }}>
              <pre style={{ margin: 0, padding: 10, overflowX: "auto" }}>
                {JSON.stringify({ studentId, dashboard }, null, 2)}
              </pre>
              <pre style={{ margin: 0, padding: 10, overflowX: "auto" }}>
                {JSON.stringify({ assessments }, null, 2)}
              </pre>
              <pre style={{ margin: 0, padding: 10, overflowX: "auto" }}>
                {JSON.stringify({ results }, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </div>

      {/* Existing navigation buttons (unchanged) */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <Button
          style={{ width: "100%" }}
          onClick={() => navigate("/student/onboarding")}
        >
          Onboarding / Context
        </Button>

        <Button
          style={{ width: "100%" }}
          onClick={() => navigate("/student/assessment")}
        >
          Start / Resume Assessment
        </Button>

        <Button
          style={{ width: "100%" }}
          onClick={() => navigate("/student/results/latest")}
        >
          View Latest Results
        </Button>

        <Button
          style={{ width: "100%" }}
          onClick={() => navigate("/student/results/history")}
        >
          Results History
        </Button>

        <Button
          style={{ width: "100%" }}
          onClick={() => {
            if (!studentId) return navigate("/student/consent");
            navigate(`/student/reports/${studentId}`);
          }}
        >
          Report (placeholder)
        </Button>

        <Button
          style={{ width: "100%" }}
          onClick={() => navigate("/student/careers/1")}
        >
          Career Detail (placeholder)
        </Button>

        <Button
          variant="secondary"
          style={{ width: "100%" }}
          onClick={() => navigate("/student/consent")}
        >
          Consent (if minor)
        </Button>

        <div style={{ marginTop: 10 }}>
          <Link to="/">← Home</Link>
        </div>
      </div>
    </SkeletonPage>
  );
}
