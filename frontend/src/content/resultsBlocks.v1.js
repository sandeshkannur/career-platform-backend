// frontend/src/content/resultsBlocks.v1.js
// Versioned, UI-friendly copy + block config for Results page.
// Keep this data-driven so the UI can render blocks consistently across pages.

export function getResultsBlocksV1({ result }) {
  // result is one item from GET /v1/students/{id}/results -> results[]
  const recommendedStream = result?.recommended_stream || null;
  const topCareers = Array.isArray(result?.top_careers) ? result.top_careers : [];

  return {
    recommendations: {
      title: "Recommendations",
      blocks: [
        {
          key: "recommended_stream",
          title: "Recommended stream",
          value:
            recommendedStream ||
            "Not available yet",
          helper:
            recommendedStream
              ? null
              : "This will appear once your stream mapping is generated.",
        },
        {
          key: "top_careers",
          title: "Top careers",
          // We keep the value normalized; UI decides how to render list vs empty.
          value: topCareers,
          emptyText:
            "Not available yet (we’ll show your top career matches here once they’re generated).",
          maxItems: 5,
        },
      ],
      footer:
        "We’ll keep improving the explanation and add more detailed “why this fits you” insights over time.",
    },
  };
}

/**
 * Normalizes a top_careers item for display.
 * Supports both string items and object items.
 */
export function formatTopCareerLabel(item, idx) {
  if (typeof item === "string") return item;
  return (
    item?.name ||
    item?.career_name ||
    item?.title ||
    `Career #${idx + 1}`
  );
}

export function formatTopCareerScore(item) {
  if (!item || typeof item === "string") return null;
  return item?.score ?? item?.match_score ?? item?.percent ?? null;
}
