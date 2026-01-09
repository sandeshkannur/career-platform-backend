// src/pages/student/StudentAssessmentRunPage.jsx
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

const DRAFT_PREFIX = "__ASSESSMENT_RUN_DRAFT_V1__";

/**
 * Assessment Runner — Step 2 (UI-only)
 * - Deterministic question set (local)
 * - One question per screen (mobile-friendly by default)
 * - Next disabled until answered
 * - Save stores progress in sessionStorage
 * - Last question -> /student/assessment/submit/:assessmentId
 *
 * Step 3+ will wire this to backend question payloads + persistence.
 */
export default function StudentAssessmentRunPage() {
  const navigate = useNavigate();
  const { assessmentId } = useParams();

  // Deterministic local question bank (placeholder until backend wiring)
  const QUESTIONS = useMemo(
    () => [
      {
        id: "q1",
        text: "I enjoy solving challenging problems.",
        options: ["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"],
      },
      {
        id: "q2",
        text: "I prefer working with people over working alone.",
        options: ["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"],
      },
      {
        id: "q3",
        text: "I like learning new tools or skills quickly.",
        options: ["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"],
      },
    ],
    []
  );

  const storageKey = useMemo(() => {
    // Keep deterministic even if assessmentId missing
    return `${DRAFT_PREFIX}:${assessmentId || "unknown"}`;
  }, [assessmentId]);

  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({}); // { [questionId]: optionText }
  const [loaded, setLoaded] = useState(false);

  const current = QUESTIONS[index];

  // Load draft (if any)
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (!raw) {
        setLoaded(true);
        return;
      }
      const parsed = JSON.parse(raw);
      const safeIndex =
        typeof parsed?.index === "number" && parsed.index >= 0 ? parsed.index : 0;
      const safeAnswers = parsed?.answers && typeof parsed.answers === "object" ? parsed.answers : {};

      setIndex(Math.min(safeIndex, QUESTIONS.length - 1));
      setAnswers(safeAnswers);
      setLoaded(true);
    } catch {
      setLoaded(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  const selected = current ? answers[current.id] : null;
  const isLast = index === QUESTIONS.length - 1;

  function choose(option) {
    setAnswers((a) => ({ ...a, [current.id]: option }));
  }

  function handleBack() {
    if (index > 0) {
      setIndex((i) => i - 1);
      return;
    }
    // Back from first question -> intro page
    navigate("/student/assessment", { replace: true });
  }

  function handleSave() {
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({
          index,
          answers,
          savedAt: new Date().toISOString(),
        })
      );
      alert("Progress saved (local draft).");
    } catch {
      alert("Unable to save progress in this browser/session.");
    }
  }

  function handleNext() {
    if (!selected) return;

    if (!isLast) {
      setIndex((i) => i + 1);
      return;
    }

    // Last question -> submit page (existing route pattern)
    navigate(`/student/assessment/submit/${assessmentId || "123"}`);
  }

  if (!loaded) {
    return (
      <SkeletonPage
        title="Assessment in Progress"
        subtitle="Loading your assessment…"
        actions={<Button variant="secondary" onClick={() => navigate("/student/assessment")}>Back</Button>}
      >
        <p>Loading…</p>
      </SkeletonPage>
    );
  }

  if (!current) {
    return (
      <SkeletonPage
        title="Assessment in Progress"
        subtitle="No questions available."
        actions={<Button variant="secondary" onClick={() => navigate("/student/assessment")}>Back</Button>}
      >
        <p>Unable to load questions.</p>
      </SkeletonPage>
    );
  }

  return (
    <SkeletonPage
      title="Assessment in Progress"
      subtitle="Answer honestly. There are no right or wrong answers."
      actions={
        <>
          <Button variant="secondary" onClick={handleBack}>
            Back
          </Button>
          <Button variant="secondary" onClick={handleSave}>
            Save
          </Button>
          <Button onClick={handleNext} disabled={!selected}>
            {isLast ? "Submit" : "Next"}
          </Button>
        </>
      }
    >
      <div style={{ maxWidth: 720, display: "grid", gap: 14 }}>
        {/* Progress */}
        <div style={{ fontSize: 12, opacity: 0.75 }}>
          Question {index + 1} of {QUESTIONS.length}
          {assessmentId ? (
            <span style={{ marginLeft: 8, opacity: 0.6 }}>• Assessment ID: {assessmentId}</span>
          ) : null}
        </div>

        {/* Question */}
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <div style={{ fontWeight: 800, marginBottom: 10 }}>{current.text}</div>

          <div style={{ display: "grid", gap: 8 }}>
            {current.options.map((opt) => {
              const active = selected === opt;
              return (
                <button
                  key={opt}
                  type="button"
                  onClick={() => choose(opt)}
                  style={{
                    textAlign: "left",
                    padding: "10px 12px",
                    borderRadius: 10,
                    border: active ? "2px solid #111" : "1px solid #ddd",
                    background: active ? "#f6f6f6" : "#fff",
                    cursor: "pointer",
                  }}
                  aria-pressed={active}
                >
                  {opt}
                </button>
              );
            })}
          </div>

          {!selected ? (
            <div
              role="alert"
              style={{
                marginTop: 12,
                padding: 10,
                borderRadius: 8,
                border: "1px solid #f0c36d",
                background: "#fff9ef",
                fontSize: 13,
              }}
            >
              Select an option to continue.
            </div>
          ) : null}
        </div>

        <div style={{ fontSize: 12, opacity: 0.7 }}>
          Note: This runner is UI-only (local questions + local save). Backend question loading and
          persistence will be wired next.
        </div>
      </div>
    </SkeletonPage>
  );
}
