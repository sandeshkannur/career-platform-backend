// src/pages/student/StudentAssessmentRunPage.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";

import { getQuestionPool } from "../../api/questions";
import { deterministicPick } from "../../lib/deterministicPick";
import { loadAnswerQueue, replayAnswerQueueOnce } from "../../lib/replayQueue";

const DRAFT_PREFIX_V2 = "__ASSESSMENT_RUN_DRAFT_V2__";
const DRAFT_PREFIX_V1 = "__ASSESSMENT_RUN_DRAFT_V1__"; // legacy (migration only)
const DRAFT_SCHEMA_VERSION = 2;

const QUESTION_COUNT = 75;

/**
 * Assessment Runner (PR4)
 * - Loads question pool from backend
 * - Deterministically selects 75 questions based on attemptId
 * - Stores a local draft in sessionStorage using a versioned schema (V2)
 * - Draft is refresh-safe and can migrate legacy V1 drafts
 *
 * NOTE:
 * - Backend owns scoring. Frontend stores answers only.
 * - No submit wiring in PR4.
 */
export default function StudentAssessmentRunPage() {
  const navigate = useNavigate();
  const { attemptId } = useParams();

  const storageKey = useMemo(() => {
    return `${DRAFT_PREFIX_V2}:${attemptId || "unknown"}`;
  }, [attemptId]);

  const legacyStorageKey = useMemo(() => {
    return `${DRAFT_PREFIX_V1}:${attemptId || "unknown"}`;
  }, [attemptId]);

  const [index, setIndex] = useState(0);

  // answers: { [questionId]: { answer: string, answered_at: ISOString } }
  const [answers, setAnswers] = useState({});

  // loaded = we attempted to load any stored draft (or decided none exists)
  const [loaded, setLoaded] = useState(false);

  // Prevent autosave from overwriting storage before we load/migrate draft
  const didLoadDraftRef = useRef(false);

  const [pool, setPool] = useState(null);
  const [poolError, setPoolError] = useState(null);

  // A+ (auto-replay on open) — small, neutral UX signal
  const [syncState, setSyncState] = useState({ status: "idle", message: "" });
  const didAutoReplayRef = useRef(false);

  /* ---------------- Load question pool ---------------- */
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

  /* ---------------- Deterministically select questions ---------------- */
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

  // Stable list of selected question ids (stored in draft for audit + safety)
  const selectedQuestionIds = useMemo(() => {
    return QUESTIONS.map(
      (q) => q?.question_id ?? q?.id ?? q?.questionId ?? ""
    ).filter(Boolean);
  }, [QUESTIONS]);

  const current = QUESTIONS[index];

  /* ---------------- Draft load / migration ---------------- */
  useEffect(() => {
    function clampIndex(i, len) {
      if (typeof i !== "number" || Number.isNaN(i)) return 0;
      if (i < 0) return 0;
      if (len <= 0) return 0;
      return Math.min(i, len - 1);
    }

    function isPlainObject(v) {
      return Boolean(v) && typeof v === "object" && !Array.isArray(v);
    }

    function normalizeV2(parsed) {
      const now = new Date().toISOString();

      const safeAnswers = isPlainObject(parsed?.answers) ? parsed.answers : {};
      const normalizedAnswers = {};

      Object.keys(safeAnswers).forEach((qid) => {
        const entry = safeAnswers[qid];

        // tolerate accidental legacy string value inside V2
        if (typeof entry === "string" && entry) {
          normalizedAnswers[qid] = { answer: entry, answered_at: now };
          return;
        }

        if (
          isPlainObject(entry) &&
          typeof entry.answer === "string" &&
          entry.answer
        ) {
          normalizedAnswers[qid] = {
            answer: entry.answer,
            answered_at:
              typeof entry.answered_at === "string" ? entry.answered_at : now,
          };
        }
      });

      const qids =
        Array.isArray(parsed?.question_ids) && parsed.question_ids.length
          ? parsed.question_ids.filter(Boolean)
          : selectedQuestionIds;

      return {
        schema_version: DRAFT_SCHEMA_VERSION,
        assessment_id: attemptId || "unknown",
        question_ids: qids,
        index: clampIndex(parsed?.index ?? 0, qids.length),
        answers: normalizedAnswers,
        created_at:
          typeof parsed?.created_at === "string" ? parsed.created_at : now,
        updated_at: now,
      };
    }

    function migrateV1ToV2(v1) {
      // V1 shape: { index, answers: { [qid]: optionText }, savedAt }
      const now = new Date().toISOString();

      const v1Answers = isPlainObject(v1?.answers) ? v1.answers : {};
      const nextAnswers = {};

      Object.keys(v1Answers).forEach((qid) => {
        const val = v1Answers[qid];
        if (typeof val === "string" && val) {
          nextAnswers[qid] = {
            answer: val,
            answered_at: typeof v1?.savedAt === "string" ? v1.savedAt : now,
          };
        }
      });

      return {
        schema_version: DRAFT_SCHEMA_VERSION,
        assessment_id: attemptId || "unknown",
        question_ids: selectedQuestionIds,
        index: clampIndex(v1?.index ?? 0, selectedQuestionIds.length),
        answers: nextAnswers,
        created_at: now,
        updated_at: now,
      };
    }

    try {
      // Prefer V2
      const rawV2 = sessionStorage.getItem(storageKey);
      if (rawV2) {
        const parsed = JSON.parse(rawV2);
        const draft = normalizeV2(parsed);

        setIndex(draft.index);
        setAnswers(draft.answers);

        // Normalize persisted form (best-effort)
        sessionStorage.setItem(storageKey, JSON.stringify(draft));

        setLoaded(true);
        didLoadDraftRef.current = true;
        return;
      }

      // Fallback: migrate legacy V1 -> V2 (one-time)
      const rawV1 = sessionStorage.getItem(legacyStorageKey);
      if (rawV1) {
        const parsedV1 = JSON.parse(rawV1);
        const draft = migrateV1ToV2(parsedV1);

        setIndex(draft.index);
        setAnswers(draft.answers);

        sessionStorage.setItem(storageKey, JSON.stringify(draft));

        setLoaded(true);
        didLoadDraftRef.current = true;
        return;
      }

      setLoaded(true);
      didLoadDraftRef.current = true;
    } catch {
      setLoaded(true);
      didLoadDraftRef.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey, legacyStorageKey, attemptId, selectedQuestionIds.length]);

  /* ---------------- A+ Auto-replay on open (resume) ---------------- */
  useEffect(() => {
    // Run once per mount only
    if (didAutoReplayRef.current) return;

    // Need an assessment id to submit to
    if (!attemptId || attemptId === "unknown") return;

    // Only try when online (offline should not spam errors)
    if (typeof navigator !== "undefined" && navigator.onLine === false) return;

    // Only try if we have something queued
    const q = loadAnswerQueue();
    if (!Array.isArray(q) || q.length === 0) return;

    didAutoReplayRef.current = true;

    (async () => {
      try {
        setSyncState({ status: "syncing", message: "Syncing saved answers…" });

        const res = await replayAnswerQueueOnce(attemptId);

        if (res?.ok) {
          // We do NOT clear queue here (by design). Clearing is handled later after verification.
          console.log("[A+ auto-replay] submitted:", res.submitted, res.server);
          setSyncState({
            status: "done",
            message:
              res.submitted > 0
                ? `Synced ${res.submitted} saved answer(s).`
                : "No saved answers to sync.",
          });
        } else {
          console.warn("[A+ auto-replay] not submitted:", res);
          setSyncState({
            status: "error",
            message:
              res?.message ||
              "Could not sync saved answers automatically. You can continue normally.",
          });
        }
      } catch (e) {
        console.warn("[A+ auto-replay] error:", e);
        setSyncState({
          status: "error",
          message:
            "Could not sync saved answers automatically. You can continue normally.",
        });
      }
    })();
  }, [attemptId]);

  /* ---------------- Autosave draft on change ---------------- */
  useEffect(() => {
    if (!didLoadDraftRef.current) return;
    if (!selectedQuestionIds.length) return;

    try {
      const now = new Date().toISOString();

      // Preserve created_at if present
      let createdAt = now;
      const existingRaw = sessionStorage.getItem(storageKey);
      if (existingRaw) {
        try {
          const existing = JSON.parse(existingRaw);
          if (typeof existing?.created_at === "string")
            createdAt = existing.created_at;
        } catch {
          // ignore
        }
      }

      const draft = {
        schema_version: DRAFT_SCHEMA_VERSION,
        assessment_id: attemptId || "unknown",
        question_ids: selectedQuestionIds,
        index,
        answers,
        created_at: createdAt,
        updated_at: now,
      };

      sessionStorage.setItem(storageKey, JSON.stringify(draft));
    } catch {
      // ignore storage errors (private mode / quotas)
    }
  }, [answers, index, selectedQuestionIds, attemptId, storageKey]);

  /* ---------------- Helpers for rendering ---------------- */
  const currentId =
    current?.question_id ?? current?.id ?? current?.questionId ?? null;

  const currentText =
    current?.text ?? current?.question_text ?? current?.prompt ?? "";

  const currentOptions = Array.isArray(current?.options)
    ? current.options
    : Array.isArray(current?.choices)
    ? current.choices
    : Array.isArray(current?.answers)
    ? current.answers
    : ["Strongly Disagree", "Disagree", "Neutral", "Agree", "Strongly Agree"];

  const selected = currentId ? answers[currentId]?.answer : null;
  const isLast = index === QUESTIONS.length - 1;

  function choose(option) {
    if (!currentId) return;
    const now = new Date().toISOString();
    setAnswers((a) => ({
      ...a,
      [currentId]: { answer: option, answered_at: now },
    }));
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
      // Autosave already persists; Save is an explicit user action.
      const now = new Date().toISOString();

      // Preserve created_at if present
      let createdAt = now;
      const existingRaw = sessionStorage.getItem(storageKey);
      if (existingRaw) {
        try {
          const existing = JSON.parse(existingRaw);
          if (typeof existing?.created_at === "string")
            createdAt = existing.created_at;
        } catch {
          // ignore
        }
      }

      sessionStorage.setItem(
        storageKey,
        JSON.stringify({
          schema_version: DRAFT_SCHEMA_VERSION,
          assessment_id: attemptId || "unknown",
          question_ids: selectedQuestionIds,
          index,
          answers,
          created_at: createdAt,
          updated_at: now,
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

  // Wait for both: local draft load attempt + backend pool load attempt
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

        {/* A+ sync hint (neutral) */}
        {syncState.status !== "idle" ? (
          <div style={{ fontSize: 12, opacity: 0.75 }}>
            {syncState.message}
          </div>
        ) : null}

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
              const optText = String(opt);
              const active = selected === optText;

              return (
                <button
                  key={optText}
                  type="button"
                  onClick={() => choose(optText)}
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
                  {optText}
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
