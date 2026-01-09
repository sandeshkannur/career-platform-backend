// src/lib/deterministicPick.js
// Deterministic, auditable selection utility.
// - No dependencies
// - Stable across refresh
// - Does not mutate input arrays

function fnv1a32(str) {
  // FNV-1a 32-bit hash (deterministic, fast)
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i += 1) {
    h ^= str.charCodeAt(i);
    // h *= 16777619 (but using bit ops keeps it 32-bit)
    h = (h + (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24)) >>> 0;
  }
  return h >>> 0;
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return function rng() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Deterministically shuffle and pick the first `count` items.
 *
 * @param {Object} args
 * @param {string} args.seed - stable seed (e.g., attemptId / assessment_id)
 * @param {Array<any>} args.items - input list (not mutated)
 * @param {number} args.count - number of items to pick
 * @param {(item:any)=>string} [args.getKey] - stable key extractor used for normalization sort
 */
export function deterministicPick({ seed, items, count, getKey }) {
  const safeSeed = String(seed || "unknown");
  const list = Array.isArray(items) ? items.slice() : [];

  // Normalize order so backend ordering cannot affect selection.
  if (typeof getKey === "function") {
    list.sort((a, b) => {
      const ka = String(getKey(a) ?? "");
      const kb = String(getKey(b) ?? "");
      return ka.localeCompare(kb);
    });
  }

  const rng = mulberry32(fnv1a32(safeSeed));

  // Fisher–Yates shuffle (deterministic due to RNG)
  for (let i = list.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = list[i];
    list[i] = list[j];
    list[j] = tmp;
  }

  const n = Math.max(0, Number(count) || 0);
  return list.slice(0, n);
}
