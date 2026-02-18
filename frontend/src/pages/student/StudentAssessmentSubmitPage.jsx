// src/pages/student/StudentAssessmentSubmitPage.jsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

import { getAssessment, postAssessmentResponses, submitAssessment } from "../../api/assessments";

const DRAFT_PREFIX_V2 = "__ASSESSMENT_RUN_DRAFT_V2__";
const QUESTION_COUNT = 75;
function toLikertCode(value) {
  // Backend expects "1".."5"
  // UI draft currently stores labels like "Agree"
  const v = String(value || "").trim().toLowerCase();

  if (v === "strongly disagree") return "1";
  if (v === "disagree") return "2";
  if (v === "neutral") return "3";
  if (v === "agree") return "4";
  if (v === "strongly agree") return "5";

  // If already numeric "1".."5", pass through
  if (/^[1-5]$/.test(v)) return v;

  return null;
}
function readDraft(storageKey) {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export default function StudentAssessmentSubmitPage() {
  const navigate = useNavigate();
  const { attemptId } = useParams();

  const storageKey = useMemo(() => {
    return `${DRAFT_PREFIX_V2}:${attemptId || "unknown"}`;
  }, [attemptId]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [serverQuestionIds, setServerQuestionIds] = useState([]);

  // Read once per render (draft is autosaved on run page)
  const draft = useMemo(() => readDraft(storageKey), [storageKey]);
    useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!attemptId) return;

      try {
        const a = await getAssessment(attemptId);

        // Expecting { question_ids: [...] } from backend
        const ids = Array.isArray(a?.question_ids) ? a.question_ids : [];

        if (!cancelled) setServerQuestionIds(ids);
      } catch (e) {
        // Don't hard fail here; draft may still exist
        if (!cancelled) {
          setError(e?.detail || e?.message || "Failed to load assessment from server.");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [attemptId]);

  const questionIds = serverQuestionIds.length
    ? serverQuestionIds
    : Array.isArray(draft?.question_ids)
      ? draft.question_ids
      : [];
  const answersObj = draft?.answers && typeof draft.answers === "object" ? draft.answers : {};

  const answeredCount = useMemo(() => {
    return questionIds.reduce((acc, qid) => {
      const a = answersObj?.[qid]?.answer;
      return acc + (typeof a === "string" && a ? 1 : 0);
    }, 0);
  }, [questionIds, answersObj]);

  const missingCount = Math.max(0, questionIds.length - answeredCount);

  const canSubmit =
    Boolean(attemptId) &&
    questionIds.length === QUESTION_COUNT &&
    answeredCount === QUESTION_COUNT &&
    !busy;

  const handleBack = useCallback(() => {
    navigate(`/student/assessment/run/${attemptId || "unknown"}`, { replace: true });
  }, [navigate, attemptId]);

  const handleConfirmSubmit = useCallback(async () => {
    setError(null);

    if (!attemptId) {
      setError("Missing attempt id. Please restart the assessment.");
      return;
    }

    if (!draft) {
      setError("No saved draft found for this assessment. Please return and answer the questions.");
      return;
    }

    if (questionIds.length !== QUESTION_COUNT) {
      setError(
        `Invalid question set. Expected ${QUESTION_COUNT} questions but found ${questionIds.length}. Please return to the assessment run.`
      );
      return;
    }

    if (answeredCount !== QUESTION_COUNT) {
      setError(
        `Assessment incomplete. Answered ${answeredCount}/${QUESTION_COUNT}. Please return and complete all questions.`
      );
      return;
    }

    const responses = questionIds.map((qid) => {
      const code = toLikertCode(answersObj?.[qid]?.answer);

      return {
        question_id: qid,
        answer: code,
        idempotency_key: `attempt:${attemptId}:q:${qid}`,
      };
    });

    const invalid = responses.find((r) => !r.answer);
    if (invalid) {
      setError(
        `Invalid answer value for question_id=${invalid.question_id}. Please go back and reselect the option.`
      );
      return;
    }

    setBusy(true);
    try {
      // 2) Persist responses first (backend authoritative)
      await postAssessmentResponses(attemptId, responses);

      // 3) Then trigger scoring / finalization
      await submitAssessment(attemptId, {});

      // Clear local draft on success
      try {
        sessionStorage.removeItem(storageKey);
      } catch {
        // ignore storage failures
      }

      // Navigate to latest results page (PR6 will render backend results)
      navigate("/student/results/latest", { replace: true });
    } catch (e) {
      setError(e?.detail || e?.message || "Submit failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }, [attemptId, draft, questionIds, answeredCount, answersObj, navigate, storageKey]);

  // Friendly empty/invalid states
  const invalidDraft =
    !draft ||
    !attemptId ||
    questionIds.length !== QUESTION_COUNT;

  return (
    <SkeletonPage
      title="Submit Assessment"
      subtitle="Review completion status before submitting."
      actions={
        <>
          <Button variant="secondary" onClick={handleBack} disabled={busy}>
            Back
          </Button>
          <Button onClick={handleConfirmSubmit} disabled={!canSubmit}>
            {busy ? "Submitting..." : "Confirm & Submit"}
          </Button>
        </>
      }
      empty={invalidDraft}
      emptyTitle="Nothing to submit yet"
      emptyDescription="Return to the assessment run and complete all questions before submitting."
    >
      <div style={{ maxWidth: 720, display: "grid", gap: 14 }}>
        <div style={{ fontSize: 13, opacity: 0.85 }}>
          Attempt ID: <b>{attemptId || "unknown"}</b>
        </div>

        <div style={{ padding: 12, border: "1px solid #ddd", borderRadius: 8 }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>Completion summary</div>
          <div style={{ fontSize: 13, opacity: 0.9 }}>
            Selected questions: <b>{questionIds.length}</b> / {QUESTION_COUNT}
          </div>
          <div style={{ fontSize: 13, opacity: 0.9 }}>
            Answered: <b>{answeredCount}</b> / {QUESTION_COUNT}
            {missingCount ? (
              <span style={{ marginLeft: 8, opacity: 0.8 }}>
                (missing {missingCount})
              </span>
            ) : null}
          </div>
        </div>

        {error ? (
          <div
            role="alert"
            style={{
              padding: 10,
              borderRadius: 8,
              border: "1px solid #f0c36d",
              background: "#fff9ef",
              fontSize: 13,
            }}
          >
            {error}
          </div>
        ) : null}

        <div style={{ fontSize: 12, opacity: 0.7 }}>
          Note: Submitting sends exactly {QUESTION_COUNT} responses to the backend for scoring.
          Scoring remains backend-owned.
        </div>
      </div>
    </SkeletonPage>
  );
}
