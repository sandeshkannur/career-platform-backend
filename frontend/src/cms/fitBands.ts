export type FitBandKey =
  | "high_potential"
  | "strong"
  | "promising"
  | "developing"
  | "exploring";

/**
 * Canonical fit-band CMS keys.
 * These keys are STABLE and language-agnostic.
 * UI must NEVER hardcode labels.
 */
export const FIT_BAND_LABEL_KEY: Record<FitBandKey, string> = {
  high_potential: "student.results.fit_band.high_potential.label",
  strong: "student.results.fit_band.strong.label",
  promising: "student.results.fit_band.promising.label",
  developing: "student.results.fit_band.developing.label",
  exploring: "student.results.fit_band.exploring.label",
};

/**
 * Optional short descriptions per band (also CMS-driven).
 */
export const FIT_BAND_DESC_KEY: Record<FitBandKey, string> = {
  high_potential: "student.results.fit_band.high_potential.desc",
  strong: "student.results.fit_band.strong.desc",
  promising: "student.results.fit_band.promising.desc",
  developing: "student.results.fit_band.developing.desc",
  exploring: "student.results.fit_band.exploring.desc",
};
