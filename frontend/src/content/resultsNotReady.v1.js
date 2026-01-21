// Versioned content block for "Results not ready" UX.
// NON-NEGOTIABLE: UI renders blocks; copy is not hardcoded in components.

export const resultsNotReady_v1 = {
  version: "v1",
  blocks: [
    {
      type: "hero",
      title: "Your results aren’t ready yet",
      body:
        "That’s normal if the assessment hasn’t been submitted yet, or if the connection dropped before completion.",
      tone: "neutral",
    },
    {
      type: "info_list",
      title: "What you can do next",
      items: [
        "Resume where you left off (if an assessment is still active).",
        "Or start a fresh attempt if you want to answer again calmly.",
      ],
      tone: "neutral",
    },
    {
      type: "cta_row",
      primaryCta: {
        label: "Go to assessment",
        // Keep this route aligned to your existing student assessment entry page.
        // If your app uses a different route, change ONLY this path (do not hardcode elsewhere).
        to: "/student/assessment",
      },
      secondaryCta: {
        label: "Go to dashboard",
        to: "/student/dashboard",
      },
      note:
        "No pressure — take your time. Your answers are used only to generate explainable guidance.",
    },
  ],
};

export default resultsNotReady_v1;
