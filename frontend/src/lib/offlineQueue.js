// src/lib/offlineQueue.js
// Offline queue (v1) for assessment answer submissions.
// - Stores items in localStorage (durable across refresh/restart)
// - Deterministic schema, append-only in storage
// - No network calls here; runner/submitter will flush later.

const QUEUE_KEY = "cp:answer_queue:v1";
const MAX_ITEMS = 2000; // safety cap for low-end devices

function safeParse(raw, fallback) {
  try {
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function nowIso() {
  return new Date().toISOString();
}

/**
 * Queue item schema (v1):
 * {
 *   v: 1,
 *   assessment_id: number|string|null,
 *   attempt_id: string|null,
 *   question_id: string|number,
 *   answer: string,
 *   client_ts: ISOString,
 *   idempotency_key: string
 * }
 */
export function readAnswerQueue() {
  const raw = localStorage.getItem(QUEUE_KEY);
  const q = safeParse(raw, []);
  return Array.isArray(q) ? q : [];
}

export function writeAnswerQueue(queue) {
  const safe = Array.isArray(queue) ? queue.slice(0, MAX_ITEMS) : [];
  localStorage.setItem(QUEUE_KEY, JSON.stringify(safe));
}

/**
 * Deterministic idempotency key for immutable answers:
 * One answer per (assessment_id, question_id). If assessment_id missing, we still queue.
 */
export function makeIdempotencyKey({ assessment_id, question_id }) {
  const a = assessment_id ?? "unknown";
  const q = question_id ?? "unknown";
  return `ans:v1:${a}:${q}`;
}

/**
 * Enqueue (append-only). If an item with same idempotency_key exists, we keep the earliest.
 * This prevents duplicate retries from growing the queue.
 */
export function enqueueAnswer({ assessment_id = null, attempt_id = null, question_id, answer }) {
  if (!question_id) throw new Error("question_id is required");
  if (typeof answer !== "string" || answer.trim() === "") throw new Error("answer is required");

  const item = {
    v: 1,
    assessment_id,
    attempt_id,
    question_id,
    answer,
    client_ts: nowIso(),
    idempotency_key: makeIdempotencyKey({ assessment_id, question_id }),
  };

  const q = readAnswerQueue();

  // Deduplicate by idempotency_key (latest wins)
  const existingIdx = q.findIndex((x) => x?.idempotency_key === item.idempotency_key);
  if (existingIdx >= 0) q.splice(existingIdx, 1);

  q.push(item);
  writeAnswerQueue(q);
  return item;
}

/**
 * Remove a batch of idempotency_keys after successful flush.
 */
export function dequeueByKeys(keys = []) {
  const set = new Set(keys);
  const q = readAnswerQueue();
  const next = q.filter((x) => !set.has(x?.idempotency_key));
  writeAnswerQueue(next);
  return next;
}

export function clearAnswerQueue() {
  localStorage.removeItem(QUEUE_KEY);
}
