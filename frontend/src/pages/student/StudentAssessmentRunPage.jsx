// src/pages/student/StudentAssessmentRunPage.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";


import Button from "../../ui/Button";
import useContent from "../../hooks/useContent";

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

  const { t } = useContent("student.assessment.run");

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

  const totalQuestions = QUESTIONS.length || 1;
  const progressPct = Math.round(((index + 1) / totalQuestions) * 100);

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
      <div className="mx-auto w-full max-w-5xl px-4 py-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold">
              {t("title", "Assessment")}
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t("loading.subtitle", "Loading your assessment…")}
            </p>
          </div>

          <div className="shrink-0">
            <Button
              variant="secondary"
              onClick={() => navigate("/student/assessment")}
            >
              {t("actions.back", "Back")}
            </Button>
          </div>
        </div>

        <div className="mt-6 rounded-xl border border-[var(--border)] bg-white p-4 text-sm">
          {t("loading.body", "Loading…")}
        </div>
      </div>
    );
  }

  if (poolError) {
    return (
      <div className="mx-auto w-full max-w-5xl px-4 py-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold">
              {t("title", "Assessment")}
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t("error.subtitle", "Unable to load questions.")}
            </p>
          </div>

          <div className="shrink-0">
            <Button
              variant="secondary"
              onClick={() => navigate("/student/assessment")}
            >
              {t("actions.back", "Back")}
            </Button>
          </div>
        </div>

        <div className="mt-6 rounded-xl border border-[#f3b4b4] bg-[#fff6f6] p-4">
          <div className="text-sm font-semibold">
            {t("error.title", "Failed to load question pool")}
          </div>
          <div className="mt-1 text-sm text-[var(--text-muted)]">
            {poolError?.message ||
              t("error.fallback", "Failed to load question pool.")}
          </div>
        </div>
      </div>
    );
  }

  if (!current || !currentId || !Array.isArray(currentOptions)) {
    return (
      <div className="mx-auto w-full max-w-5xl px-4 py-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold">
              {t("title", "Assessment")}
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t("empty.subtitle", "No questions available.")}
            </p>
          </div>

          <div className="shrink-0">
            <Button
              variant="secondary"
              onClick={() => navigate("/student/assessment")}
            >
              {t("actions.back", "Back")}
            </Button>
          </div>
        </div>

        <div className="mt-6 rounded-xl border border-[var(--border)] bg-white p-4 text-sm">
          {t("empty.body", "Unable to load questions.")}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">
            {t("title", "Assessment")}
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            {t(
              "subtitle",
              "Answer honestly. There are no right or wrong answers."
            )}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button variant="secondary" onClick={handleBack}>
            {t("actions.back", "Back")}
          </Button>
          <Button variant="secondary" onClick={handleSave}>
            {t("actions.save", "Save")}
          </Button>
          <Button onClick={handleNext} disabled={!selected}>
            {isLast
              ? t("actions.submit", "Submit")
              : t("actions.next", "Next")}
          </Button>
        </div>
      </div>

      {/* Progress */}
      <div className="mt-6">
        <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
          <div>
            Question{" "}
            <span className="font-medium text-[var(--text-primary)]">
              {index + 1}
            </span>{" "}
            of{" "}
            <span className="font-medium text-[var(--text-primary)]">
              {QUESTIONS.length}
            </span>
            {attemptId ? (
              <span className="ml-2 opacity-80">
                • Attempt ID: {attemptId}
              </span>
            ) : null}
          </div>

          <div>{progressPct}%</div>
        </div>

        <div className="mt-2 h-2 w-full rounded-full bg-[var(--border)]">
          <div
            className="h-2 rounded-full bg-[var(--brand-primary)] transition-all"
            style={{ width: `${progressPct}%` }}
          />
        </div>

        {/* A+ sync hint (neutral) */}
        {syncState.status !== "idle" ? (
          <div className="mt-2 text-xs text-[var(--text-muted)]">
            {syncState.message}
          </div>
        ) : null}
      </div>

      {/* Determinism metadata (auditable) */}
      <div className="mt-3 text-xs text-[var(--text-muted)]">
        Deterministic selection: seed = attemptId, pick = {QUESTION_COUNT} (or
        fewer if pool smaller)
      </div>

      {/* Question Card */}
      <div className="mt-6 rounded-2xl border border-[var(--border)] bg-white p-6">
        <div className="text-lg font-semibold leading-snug">{currentText}</div>

        <div className="mt-4 grid gap-3">
          {currentOptions.map((opt) => {
            const optText = String(opt);
            const active = selected === optText;

            return (
              <button
                key={optText}
                type="button"
                onClick={() => choose(optText)}
                className={[
                  "w-full rounded-xl border px-4 py-3 text-left text-sm transition",
                  "hover:shadow-sm",
                  active
                    ? "border-[var(--brand-primary)] bg-[var(--bg-app)]"
                    : "border-[var(--border)] bg-white",
                ].join(" ")}
                aria-pressed={active}
              >
                <div className="font-medium text-[var(--text-primary)]">
                  {optText}
                </div>
              </button>
            );
          })}
        </div>

        {!selected ? (
          <div
            role="alert"
            className="mt-4 rounded-xl border border-[#f0c36d] bg-[#fff9ef] p-3 text-sm"
          >
             <div className="font-semibold">
               {t("helper.select_title", "Select an option to continue")}
             </div>
            <div className="mt-1 text-[var(--text-muted)]">
              {t(
                "helper.select_body",
                "You can change your answer anytime before submitting."
              )}
            </div>
          </div>
        ) : null}

        <div className="mt-5 text-xs text-[var(--text-muted)]">
          {t(
            "note.scoring",
            "Note: Scoring remains backend-owned. This runner only loads questions, selects deterministically, and stores a local draft."
          )}
        </div>
      </div>
    </div>
  );
}
