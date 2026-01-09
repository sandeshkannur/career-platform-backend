// src/pages/student/StudentAssessmentRunPage.jsx
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

import { getQuestionPool } from "../../api/questions";
import { deterministicPick } from "../../lib/deterministicPick";

const DRAFT_PREFIX = "__ASSESSMENT_RUN_DRAFT_V1__";
const QUESTION_COUNT = 75;

/**
 * Assessment Runner
 * - Loads question pool from backend
 * - Deterministically selects 75 questions based on attemptId
 * - One question per screen (mobile-friendly by default)
 * - Save stores progress in sessionStorage (draft only; PR4 will align model)
 */
export default function StudentAssessmentRunPage() {
  const navigate = useNavigate();
  const { attemptId } = useParams();

  const storageKey = useMemo(() => {
    // Keep deterministic even if attemptId missing
    return `${DRAFT_PREFIX}:${attemptId || "unknown"}`;
  }, [attemptId]);

  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({}); // { [questionId]: optionText }
  const [loaded, setLoaded] = useState(false);

  const [pool, setPool] = useState(null);
  const [poolError, setPoolError] = useState(null);

  // Load question pool
  useEffect(() => {
    let cancelled = false;

    async function loadPool() {
      setPool(null);
      setPoolError(null);

      try {
        const data = await getQuestionPool();

        // Backend contract can be either:
        // - { questions: [...] }
        // - [...]
        const questions = Array.isArray(data) ? data : data?.questions;

        if (!Array.isArray(questions)) {
          throw new Error("Invalid question pool payload (expected array).");
        }

        if (!cancelled) setPool(questions);
      } catch (e) {
        if (!cancelled) setPoolError(e);
      }
    }

    loadPool();
    return () => {
      cancelled = true;
    };
  }, [attemptId]);

  // Deterministically select questions
  const QUESTIONS = useMemo(() => {
    if (!Array.isArray(pool)) return [];

    const getKey = (q) => q?.question_id ?? q?.id ?? q?.questionId ?? "";

    return deterministicPick({
      seed: attemptId || "unknown",
      items: pool,
      count: QUESTION_COUNT,
      getKey,
    });
  }, [pool, attemptId]);

  const current = QUESTIONS[index];

  // Load draft (if any) — keeps existing behavior for now
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
      const safeAnswers =
        parsed?.answers && typeof parsed.answers === "object" ? parsed.answers : {};

      setIndex(Math.min(safeIndex, Math.max(0, QUESTIONS.length - 1)));
      setAnswers(safeAnswers);
      setLoaded(true);
    } catch {
      setLoaded(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey, QUESTIONS.length]);

  // Helpers for rendering without mutating backend payload
  const currentId =
    current?.question_id ?? current?.id ?? current?.questionId ?? null;

  const currentText =
    current?.text ?? current?.question_text ?? current?.prompt ?? "";

  const currentOptions =
    current?.options ?? current?.choices ?? current?.answers ?? [];

  const selected = currentId ? answers[currentId] : null;
  const isLast = index === QUESTIONS.length - 1;

  function choose(option) {
    if (!currentId) return;
    setAnswers((a) => ({ ...a, [currentId]: option }));
  }

  function handleBack() {
    if (index > 0) {
      setIndex((i) => i - 1);
      return;
    }
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
    navigate(`/student/assessment/submit/${attemptId || "unknown"}`);
  }

  // Wait for both: local draft load + backend pool load attempt
  const stillLoading = !loaded || (!pool && !poolError);

  if (stillLoading) {
    return (
      <SkeletonPage
        title="Assessment in Progress"
        subtitle="Loading your assessment…"
        actions={
          <Button
            variant="secondary"
            onClick={() => navigate("/student/assessment")}
          >
            Back
          </Button>
        }
      >
        <p>Loading…</p>
      </SkeletonPage>
    );
  }

  if (poolError) {
    return (
      <SkeletonPage
        title="Assessment in Progress"
        subtitle="Unable to load questions."
        actions={
          <Button
            variant="secondary"
            onClick={() => navigate("/student/assessment")}
          >
            Back
          </Button>
        }
      >
        <p>{poolError?.message || "Failed to load question pool."}</p>
      </SkeletonPage>
    );
  }

  if (!current || !currentId || !Array.isArray(currentOptions)) {
    return (
      <SkeletonPage
        title="Assessment in Progress"
        subtitle="No questions available."
        actions={
          <Button
            variant="secondary"
            onClick={() => navigate("/student/assessment")}
          >
            Back
          </Button>
        }
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
          {attemptId ? (
            <span style={{ marginLeft: 8, opacity: 0.6 }}>
              • Attempt ID: {attemptId}
            </span>
          ) : null}
        </div>

        {/* Determinism metadata (auditable) */}
        <div style={{ fontSize: 12, opacity: 0.7 }}>
          Deterministic selection: seed = attemptId, pick = {QUESTION_COUNT} (or
          fewer if pool smaller)
        </div>

        {/* Question */}
        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <div style={{ fontWeight: 800, marginBottom: 10 }}>{currentText}</div>

          <div style={{ display: "grid", gap: 8 }}>
            {currentOptions.map((opt) => {
              const active = selected === opt;
              return (
                <button
                  key={String(opt)}
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
                  {String(opt)}
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
          Note: Scoring remains backend-owned. This runner only loads questions,
          selects deterministically, and stores a local draft.
        </div>
      </div>
    </SkeletonPage>
  );
}
