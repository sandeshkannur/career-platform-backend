// frontend/src/lib/replayQueue.js
// Manual replay of offline answer queue to backend.
// IMPORTANT:
// - Backend is authoritative for scoring.
// - Replay is idempotent via idempotency_key.
// - This file does NOT auto-run; it is invoked manually for verification.

import { postAssessmentResponses } from "../api/assessments";

const QUEUE_KEY = "cp:answer_queue:v1";

/**
 * Loads the current offline queue (append-only log).
 */
export function loadAnswerQueue() {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
  } catch {
    return [];
  }
}

/**
 * Maps offline queue entries into backend contract.
 * Backend expects answer as string "1".."5".
 */
function toLikert15(answer) {
  // If already numeric 1..5, keep it
  const s = String(answer ?? "").trim();
  if (/^[1-5]$/.test(s)) return s;

  // Map common label text -> 1..5
  const map = {
    "Strongly Disagree": "1",
    "Disagree": "2",
    "Neutral": "3",
    "Agree": "4",
    "Strongly Agree": "5",
  };

  return map[s] || ""; // empty string will fail guard below (by design)
}

function mapQueueToRequest(queueItems) {
  return queueItems.map((e) => ({
    question_id: String(e.question_id),
    answer: toLikert15(e.answer),
    idempotency_key: String(e.idempotency_key || e.key || e.k || ""),
  }));
}

/**
 * Manual replay: submits all queued answers in a single batch.
 * Returns backend resume pointer response.
 *
 * NOTE: Does NOT clear the queue. We only clear after verification.
 */
export async function replayAnswerQueueOnce(assessmentId) {
  const queue = loadAnswerQueue();
  if (!queue.length) {
    return { ok: true, message: "Queue empty; nothing to replay", submitted: 0 };
  }

  const payload = mapQueueToRequest(queue);

  // Guard: ensure required fields exist to avoid backend 422
  const missing = payload.find((x) => !x.question_id || !x.answer || !x.idempotency_key);
  if (missing) {
    return {
      ok: false,
      message: "Queue has entries missing question_id/answer/idempotency_key. Not submitting.",
      sample_bad_entry: missing,
      submitted: 0,
    };
  }

  const res = await postAssessmentResponses(assessmentId, payload);
  return { ok: true, submitted: payload.length, server: res };
}
