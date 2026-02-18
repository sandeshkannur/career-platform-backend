// frontend/src/api/explainability.js
import { apiGet } from "./http";

/**
 * CMS explainability content pack.
 * Backend endpoint uses `lang` query param.
 * Returns: { version, locale, items: [{ explanation_key, text }, ...] }
 */
export async function getExplainabilityContent(lang = "en") {
  const safeLang = lang || "en";
  return apiGet(`/v1/content/explainability?lang=${encodeURIComponent(safeLang)}`);
}
