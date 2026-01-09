// src/pages/student/StudentAssessmentIntroPage.jsx
import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

import { startAssessment } from "../../api/assessments";

/**
 * Assessment UX — Step 2 (wired)
 * - Start calls backend to create an assessment run
 * - Snapshot is persisted locally for Resume
 * - Resume uses the last snapshot (if present)
 *
 * NOTE:
 * - Storage keys will be centralized later (PR8).
 * - Keep diffs minimal and deterministic.
 */
const STORAGE_KEY_LAST_RUN = "cp:last_assessment_run:v1";

function readLastRunSnapshot() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_LAST_RUN);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.assessment_id) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeLastRunSnapshot(snapshot) {
  try {
    localStorage.setItem(STORAGE_KEY_LAST_RUN, JSON.stringify(snapshot));
  } catch {
    // ignore storage failures (private mode / quotas) — Start still works
  }
}

export default function StudentAssessmentIntroPage() {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  const lastRun = useMemo(() => readLastRunSnapshot(), []);

  const goToRun = useCallback(
    (assessmentId) => {
      navigate(`/student/assessment/run/${assessmentId}`);
    },
    [navigate]
  );

  const handleStart = useCallback(async () => {
    setBusy(true);
    try {
      const data = await startAssessment();
      const assessmentId = data?.assessment_id;

      if (!assessmentId) {
        throw new Error("assessment_id missing from response");
      }

      // Persist a minimal snapshot for resume.
      // Backend may return more fields; we keep them as-is.
      writeLastRunSnapshot({ ...data, assessment_id: assessmentId });

      goToRun(assessmentId);
    } finally {
      setBusy(false);
    }
  }, [goToRun]);

  const handleResume = useCallback(() => {
    if (lastRun?.assessment_id) {
      goToRun(lastRun.assessment_id);
      return;
    }
    // If nothing to resume, behave like Start (no extra UX yet).
    handleStart();
  }, [goToRun, handleStart, lastRun]);

  return (
    <SkeletonPage
      title="Assessment"
      subtitle="Understand your strengths, preferences, and aptitude."
      actions={
        <>
          <Button variant="secondary" disabled={busy} onClick={handleResume}>
            Resume
          </Button>
          <Button disabled={busy} onClick={handleStart}>
            {busy ? "Starting..." : "Start Assessment"}
          </Button>
        </>
      }
    >
      <div style={{ maxWidth: 720, display: "grid", gap: 14 }}>
        <p style={{ marginTop: 0 }}>
          This assessment helps generate <b>deterministic</b> and <b>explainable</b>{" "}
          career recommendations based on your responses.
        </p>

        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>What to expect</div>
          <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
            <li>Answer honestly — there are no right or wrong answers.</li>
            <li>Estimated time: ~10–15 minutes (placeholder).</li>
            <li>You can resume later (progress saving will be wired next).</li>
          </ul>
        </div>

        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <div style={{ fontWeight: 800, marginBottom: 6 }}>Privacy & disclaimer</div>
          <div style={{ fontSize: 13, opacity: 0.9 }}>
            Your responses are used only to generate your recommendations and reports.
            This is a guidance tool and not a guaranteed predictor of outcomes.
          </div>
        </div>

        <div style={{ fontSize: 12, opacity: 0.7 }}>
          Note: Start creates a real assessment id via backend. Resume uses the last saved
          snapshot.
        </div>
      </div>
    </SkeletonPage>
  );
}
