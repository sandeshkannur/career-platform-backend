// src/pages/student/StudentAssessmentIntroPage.jsx
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";

import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

/**
 * Assessment UX — Step 1 (UI-only)
 * - Clear expectations + deterministic flow
 * - No backend wiring yet
 * - Start routes to the existing runner path with a placeholder id
 */
export default function StudentAssessmentIntroPage() {
  const navigate = useNavigate();

  // UI-only placeholder until Step 2 wiring (create/resume assessment id)
  const placeholderAssessmentId = useMemo(() => "123", []);

  return (
    <SkeletonPage
      title="Assessment"
      subtitle="Understand your strengths, preferences, and aptitude."
      actions={
        <>
          <Button
            variant="secondary"
            onClick={() => navigate(`/student/assessment/run/${placeholderAssessmentId}`)}
          >
            Resume
          </Button>
          <Button
            onClick={() => navigate(`/student/assessment/run/${placeholderAssessmentId}`)}
          >
            Start Assessment
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
          Note: Step 1 uses a placeholder assessment id. Next step will create/resume an
          assessment using backend APIs.
        </div>
      </div>
    </SkeletonPage>
  );
}
