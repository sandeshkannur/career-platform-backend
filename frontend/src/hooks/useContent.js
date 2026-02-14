// frontend/src/hooks/useContent.js
// CMS-ready content hook.
// Today: uses local DEFAULTS dictionary.
// Later: swap DEFAULTS for API / CMS fetch without changing component usage.

const DEFAULTS = {
  // Dashboard
  "dashboard.welcome": "Welcome back",
  "dashboard.actions.startAssessment": "Start Assessment",
  "dashboard.actions.viewResults": "View Results",
  "dashboard.actions.profile": "Profile",

  // Login
  "login.title": "Sign in",
  "login.subtitle": "Continue to your student dashboard",

  // Assessment
  "assessment.progress": "Progress",
  "assessment.next": "Next",
  "assessment.submit": "Submit",

  // Results
  "results.title": "Your Results",
  "results.subtitle": "Career recommendations based on your responses",
  "results.premium.title": "Insights",
  "results.premium.locked": "Upgrade to view detailed insights",
};

export default function useContent(sectionKey = "") {
  // sectionKey is kept for future usage (namespaced fetch, caching, locales, etc.)
  // Currently we simply use it to help callers keep intent clear.
  const prefix = sectionKey ? `${sectionKey}.` : "";

  function t(key, fallback = "") {
    const fullKey = key.startsWith(prefix) ? key : `${prefix}${key}`;
    const value = DEFAULTS[fullKey];

    if (value === undefined || value === null || value === "") {
      return fallback || fullKey;
    }
    return value;
  }

  return { t };
}