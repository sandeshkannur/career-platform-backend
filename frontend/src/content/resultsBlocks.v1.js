/**
 * frontend/src/content/resultsBlocks.v1.js
 * Versioned, UI-friendly copy + block config for Results page.
 *
 * Principles:
 * - CMS-driven labels (locale-ready)
 * - Student-safe: never expose numbers/scores/weights/percentages
 * - Data-driven blocks for consistent rendering
 */
import { getFitBandsV1 } from "./fitBands.v1";
import { getAssociatedQualitiesV1 } from "./associatedQualities.v1";
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
          value: recommendedStream || "Not available yet",
          helper: recommendedStream ? null : "This will appear once your stream mapping is generated.",
        },
        {
          key: "top_careers",
          title: "Top careers",
          // Keep normalized; UI decides list vs empty state.
          value: topCareers,
          emptyText: "Not available yet (we’ll show your top career matches here once they’re generated).",
          maxItems: 3,
        },
      ],
      footer: "We’ll keep improving the explanation and add more detailed “why this fits you” insights over time.",
    },

    /**
     * Fit-band label/description keys (canonical + locale-ready).
     * UI should resolve these keys via your locale pack / CMS resolver.
     */
    fitBands: getFitBandsV1(),
    
    /**
     * Paid / Premium extensions (CMS-only for now).
     * UI decides when to render based on plan/tier.
     */
    associatedQualities: getAssociatedQualitiesV1({
      fitBandKey: topCareers?.[0]?.fit_band_key || "exploring",
    }),
  };
}

/**
 * Normalizes a top_careers item for display (student-safe).
 * Supports both string items and object items.
 */
export function formatTopCareerLabel(item, idx) {
  if (typeof item === "string") return item;

  // Prefer the seeded payload keys first
  return (
    item?.career_title ||
    item?.title ||
    item?.career_name ||
    item?.name ||
    `Career #${idx + 1}`
  );
}

/**
 * Student-safe: never show numeric scores/percentages.
 * Always return null.
 */
export function formatTopCareerScore() {
  return null;
}
