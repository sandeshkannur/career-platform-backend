// src/pages/StudentDashboardPage.jsx
import { Link, useNavigate } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";

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
    <div className="mx-auto w-full max-w-5xl px-4 py-6">
      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">Student Dashboard</h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            {sessionUser?.full_name
              ? `Welcome, ${sessionUser.full_name}. Choose what you want to do next.`
              : "Choose what you want to do next."}
          </p>
        </div>

        <div className="shrink-0">
          <Button onClick={logout}>Logout</Button>
        </div>
      </div>

      {/* Step 1: Consent Required Indicator (READ-ONLY) */}
      {showConsentRequired && (
        <div className="mt-5 rounded-xl border border-[#f0c36d] bg-[#fff9ef] p-4">
          <div className="text-sm font-semibold">Guardian consent required ⚠️</div>
          <div className="mt-1 text-sm text-[var(--text-muted)]">
            Your account is marked as a minor. Please complete guardian consent
            verification to unlock reports and continue.
          </div>
        </div>
      )}

      {/* Step 1: Consent Verified Indicator (READ-ONLY) */}
      {showConsentVerified && (
        <div className="mt-5 rounded-xl border border-[#cfe9d6] bg-[#f3fff6] p-4">
          <div className="text-sm font-semibold">Parental consent verified ✅</div>
          <div className="mt-1 text-sm text-[var(--text-muted)]">
            Your guardian consent is verified. You can continue using the platform.
          </div>
        </div>
      )}

      {/* Read-only data section (temporary but extremely useful for schema validation) */}
      <div className="mt-6">
        {!studentId && (
          <div className="rounded-xl border border-[var(--border)] bg-white p-4">
            <div className="text-sm font-semibold">Session</div>
            <div className="mt-2 text-sm text-[var(--text-muted)]">
              Could not determine <code>studentId</code> from{" "}
              <code>sessionUser</code>.
              <br />
              Please share your <code>/v1/auth/me</code> payload field name for the
              student id.
            </div>
          </div>
        )}

        {studentId && loading && (
          <div className="rounded-xl border border-[var(--border)] bg-white p-4 text-sm">
            Loading dashboard data…
          </div>
        )}

        {studentId && error && (
          <div className="rounded-xl border border-[#f3b4b4] bg-[#fff6f6] p-4">
            <div className="text-sm font-semibold">
              Failed to load dashboard data
              {error.status ? ` (HTTP ${error.status})` : ""}
            </div>
            <div className="mt-1 text-sm text-[var(--text-muted)]">
              {error.message}
            </div>
            <div className="mt-3">
              <Button variant="secondary" onClick={() => window.location.reload()}>
                Retry
              </Button>
            </div>
          </div>
        )}

        {studentId && !loading && !error && (dashboard || assessments || results) && (
          <details className="rounded-xl border border-[var(--border)] bg-white">
            <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold">
              Backend Data (temporary debug view)
              <span className="ml-2 text-xs font-normal text-[var(--text-muted)]">
                (click to expand)
              </span>
            </summary>

            <div className="grid gap-3 px-4 pb-4">
              <pre className="m-0 overflow-x-auto rounded-lg bg-[var(--bg-app)] p-3 text-xs">
                {JSON.stringify({ studentId, dashboard }, null, 2)}
              </pre>
              <pre className="m-0 overflow-x-auto rounded-lg bg-[var(--bg-app)] p-3 text-xs">
                {JSON.stringify({ assessments }, null, 2)}
              </pre>
              <pre className="m-0 overflow-x-auto rounded-lg bg-[var(--bg-app)] p-3 text-xs">
                {JSON.stringify({ results }, null, 2)}
              </pre>
            </div>
          </details>
        )}
      </div>

      {/* Action cards */}
      <div className="mt-6">
        <div className="grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => navigate("/student/onboarding")}
            className="rounded-xl border border-[var(--border)] bg-white p-4 text-left transition hover:shadow-sm"
          >
            <div className="text-sm font-semibold">Onboarding / Context</div>
            <div className="mt-1 text-sm text-[var(--text-muted)]">
              Add optional context to improve recommendations.
            </div>
          </button>

          <button
            type="button"
            onClick={() => navigate("/student/assessment")}
            className="rounded-xl border border-[var(--border)] bg-white p-4 text-left transition hover:shadow-sm"
          >
            <div className="text-sm font-semibold">Start / Resume Assessment</div>
            <div className="mt-1 text-sm text-[var(--text-muted)]">
              Continue your assessment journey.
            </div>
          </button>

          <button
            type="button"
            onClick={() => navigate("/student/results/latest")}
            className="rounded-xl border border-[var(--border)] bg-white p-4 text-left transition hover:shadow-sm"
          >
            <div className="text-sm font-semibold">View Latest Results</div>
            <div className="mt-1 text-sm text-[var(--text-muted)]">
              See your latest career recommendations.
            </div>
          </button>

          <button
            type="button"
            onClick={() => navigate("/student/results/history")}
            className="rounded-xl border border-[var(--border)] bg-white p-4 text-left transition hover:shadow-sm"
          >
            <div className="text-sm font-semibold">Results History</div>
            <div className="mt-1 text-sm text-[var(--text-muted)]">
              View all your previous submissions.
            </div>
          </button>

          <button
            type="button"
            onClick={() => {
              if (!studentId) return navigate("/student/consent");
              navigate(`/student/reports/${studentId}`);
            }}
            className="rounded-xl border border-[var(--border)] bg-white p-4 text-left transition hover:shadow-sm"
          >
            <div className="text-sm font-semibold">Report (placeholder)</div>
            <div className="mt-1 text-sm text-[var(--text-muted)]">
              Downloadable report experience (coming soon).
            </div>
          </button>

          <button
            type="button"
            onClick={() => navigate("/student/careers/1")}
            className="rounded-xl border border-[var(--border)] bg-white p-4 text-left transition hover:shadow-sm"
          >
            <div className="text-sm font-semibold">Career Detail (placeholder)</div>
            <div className="mt-1 text-sm text-[var(--text-muted)]">
              Deep dive into a career explanation (coming soon).
            </div>
          </button>

          <button
            type="button"
            onClick={() => navigate("/student/consent")}
            className="rounded-xl border border-[var(--border)] bg-white p-4 text-left transition hover:shadow-sm"
          >
            <div className="text-sm font-semibold">Consent (if minor)</div>
            <div className="mt-1 text-sm text-[var(--text-muted)]">
              Verify guardian consent if required.
            </div>
          </button>
        </div>

        <div className="mt-4">
          <Link
            to="/"
            className="text-sm text-[var(--brand-primary)] hover:underline"
          >
            ← Home
          </Link>
        </div>
      </div>
    </div>
  );
}
