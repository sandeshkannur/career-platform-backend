import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { apiGet } from "../../apiClient";
import SkeletonPage from "../../ui/SkeletonPage";
import Button from "../../ui/Button";
import { useSession } from "../../hooks/useSession";
import { getContextImpactCopyV1 } from "../../content/contextImpact.v1";

import { getResultsBlocksV1 } from "../../content/resultsBlocks.v1";
import resultsNotReady_v1 from "../../content/resultsNotReady.v1";

function PencilIcon({ size = 14 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      style={{ display: "inline-block" }}
    >
      <path
        fill="currentColor"
        d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zm2.92 2.33H5v-.92l8.06-8.06.92.92L5.92 19.58zM20.71 7.04a1.003 1.003 0 0 0 0-1.42l-2.34-2.34a1.003 1.003 0 0 0-1.42 0l-1.83 1.83 3.75 3.75 1.84-1.82z"
      />
    </svg>
  );
}

function ResultsNotReadyView({ content }) {
  const blocks = content?.blocks || [];

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: 16 }}>
      {blocks.map((b, idx) => {
        if (b.type === "hero") {
          return (
            <div key={idx} style={{ marginBottom: 16 }}>
              <h1 style={{ fontSize: 22, margin: "0 0 8px 0" }}>{b.title}</h1>
              <p style={{ margin: 0, lineHeight: 1.5 }}>{b.body}</p>
            </div>
          );
        }

        if (b.type === "info_list") {
          return (
            <div key={idx} style={{ marginBottom: 16 }}>
              <h2 style={{ fontSize: 16, margin: "0 0 8px 0" }}>{b.title}</h2>
              <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.6 }}>
                {(b.items || []).map((it, j) => (
                  <li key={j}>{it}</li>
                ))}
              </ul>
            </div>
          );
        }

        if (b.type === "cta_row") {
          return (
            <div key={idx} style={{ marginTop: 20 }}>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <Button onClick={() => (window.location.href = b.primaryCta.to)}>
                  {b.primaryCta.label}
                </Button>

                <Button
                  variant="secondary"
                  onClick={() => (window.location.href = b.secondaryCta.to)}
                >
                  {b.secondaryCta.label}
                </Button>
              </div>

              {b.note ? (
                <p
                  style={{
                    marginTop: 12,
                    marginBottom: 0,
                    lineHeight: 1.5,
                    opacity: 0.85,
                  }}
                >
                  {b.note}
                </p>
              ) : null}
            </div>
          );
        }

        return null;
      })}
    </div>
  );
}
function TopCareerCard({ career, fitBandsCopy, idx }) {
  const band = fitBandsCopy?.[career?.fit_band_key] || null;

  const bandLabel = band?.label || career?.fit_band_key || "Fit band";
  const bandDesc = band?.desc || "";

  const title =
    career?.career_title ||
    career?.title ||
    career?.career_name ||
    career?.name ||
    `Career #${idx + 1}`;

  const cluster = career?.cluster_title || "";
  const drivers = Array.isArray(career?.drivers) ? career.drivers.slice(0, 3) : [];

  return (
    <div className="card top-career-card">
      <div className="top-career-card__header">
        <div className="top-career-card__titleWrap">
          <div className="top-career-card__title">{title}</div>

          {cluster ? (
            <div className="text-muted top-career-card__cluster">{cluster}</div>
          ) : null}
        </div>

        <div
          className="top-career-card__bandPill"
          aria-label={`Fit band: ${bandLabel}`}
          title={bandDesc || bandLabel}
        >
          {bandLabel}
        </div>
      </div>

      {bandDesc ? (
        <div className="text-muted top-career-card__bandDesc">{bandDesc}</div>
      ) : null}

      {drivers.length > 0 ? (
        <ul className="top-career-card__drivers">
          {drivers.map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
export default function StudentResultsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sessionUser } = useSession();

  const canSeeScores =
    sessionUser?.role === "admin" || sessionUser?.role === "counsellor";

  const resultsTier =
    (sessionUser?.subscription_tier ||
      sessionUser?.tier ||
      sessionUser?.plan ||
      localStorage.getItem("CP_RESULTS_TIER") ||
      "free")
      .toString()
      .toLowerCase();

  const isPaidOrPremium = resultsTier === "paid" || resultsTier === "premium";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);
  const [ctx, setCtx] = useState(null);

  const contentLocale = useMemo(() => {
    const raw =
      sessionUser?.locale ||
      sessionUser?.preferred_locale ||
      (typeof navigator !== "undefined" ? navigator.language : "en");
    return (raw || "en").toString().split(/[-_]/)[0].toLowerCase();
  }, [sessionUser]);

  const [explainRes, setExplainRes] = useState({ facets: [], aqs: [] });
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState("");

  const lastExplainSigRef = useRef("");

  const selectedAssessmentId = useMemo(() => {
    const fromState =
      location?.state?.assessment_id ??
      location?.state?.selectedAssessmentId ??
      null;

    const params = new URLSearchParams(location?.search || "");
    const fromQuery = params.get("assessment_id");

    if (fromState != null) return Number(fromState);
    if (fromQuery != null && fromQuery !== "") return Number(fromQuery);

    return null;
  }, [location?.state, location?.search]);

  const studentId = sessionUser?.student_profile?.student_id ?? null;

  useEffect(() => {
    async function load() {
      if (!studentId) {
        setError("Student not ready");
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError("");
        const res = await apiGet(`/v1/students/${studentId}/results`);
        setData(res);
      } catch (e) {
        setError(
          e?.message ||
            "Results not ready. Please try again after submitting assessment."
        );
      } finally {
        setLoading(false);
      }
    }

    if (studentId) load();
  }, [studentId]);

  const selectedResult = useMemo(() => {
    if (!Array.isArray(data?.results) || data.results.length === 0) return null;

    if (selectedAssessmentId != null) {
      const match = data.results.find((r) => r.assessment_id === selectedAssessmentId);
      return match ?? data.results[0];
    }

    return data.results[0];
  }, [data, selectedAssessmentId]);

  const backendBlocks = useMemo(() => {
    return Array.isArray(selectedResult?.blocks) ? selectedResult.blocks : [];
  }, [selectedResult]);

  const facetKeys = useMemo(() => {
    const facetBlock = backendBlocks.find((b) => b?.block_type === "FACET_INSIGHTS");
    return Array.isArray(facetBlock?.facet_keys) ? facetBlock.facet_keys : [];
  }, [backendBlocks]);

  const aqKeys = useMemo(() => {
    const aqBlock = backendBlocks.find((b) => b?.block_type === "ASSOCIATED_QUALITIES");
    return Array.isArray(aqBlock?.aq_keys) ? aqBlock.aq_keys : [];
  }, [backendBlocks]);

  const hasPremiumSignals = facetKeys.length > 0 || aqKeys.length > 0;

  useEffect(() => {
    setCtx(null);
  }, [selectedResult?.assessment_id]);

  useEffect(() => {
    async function loadExplainability() {
      if (!isPaidOrPremium || !hasPremiumSignals) {
        setExplainRes({ facets: [], aqs: [] });
        setExplainError("");
        setExplainLoading(false);
        return;
      }

      try {
        setExplainLoading(true);
        setExplainError("");

        // Build a single keys list (backend expects `keys=...`)
        const combinedKeys = Array.from(
          new Set([...(facetKeys || []), ...(aqKeys || [])].filter(Boolean))
        );

        // If keys vanish, clear state calmly
        if (combinedKeys.length === 0) {
          lastExplainSigRef.current = "";
          setExplainRes({ facets: [], aqs: [] });
          setExplainError("");
          return;
        }
        const version = selectedResult?.results_payload_version || "v1";
        const locale = contentLocale || "en";
        const sig = `${version}|${locale}|${combinedKeys.join(",")}`;

        // Guard against duplicate calls (dev strict mode / dependency churn)
        if (lastExplainSigRef.current === sig) return;
        lastExplainSigRef.current = sig;
        const params = new URLSearchParams();
        params.set("version", version);
        params.set("locale", locale);
        params.set("keys", combinedKeys.join(","));

        const res = await apiGet(`/v1/content/explainability?${params.toString()}`);
        const items = Array.isArray(res?.items) ? res.items : [];

        // Build lookup: { explanation_key -> text }
        const map = {};
        for (const it of items) {
          const k = (it?.explanation_key || "").toString().trim();
          const v = (it?.text || "").toString().trim();
          if (!k || !v) continue;
          map[k] = v;
        }

        // Preserve original ordering from blocks
        const facets = (facetKeys || []).map((k) => map[k]).filter(Boolean);
        const aqs = (aqKeys || []).map((k) => map[k]).filter(Boolean);

        setExplainRes({ facets, aqs });
      } catch (e) {
        setExplainError(e?.message || "Could not load insights yet.");
        setExplainRes({ facets: [], aqs: [] });
      } finally {
        setExplainLoading(false);
      }
    }

    loadExplainability();
  }, [isPaidOrPremium, hasPremiumSignals, contentLocale, facetKeys, aqKeys, selectedResult?.results_payload_version]);

  function labelOrNotShared(v) {
    const val = (v ?? "unknown").toString().trim();
    return !val || val.toLowerCase() === "unknown" ? "Not shared yet" : val;
  }

  const isContextUnknown = useMemo(() => {
    if (!ctx) return true;
    const fields = [ctx.ses_band, ctx.education_board, ctx.support_level, ctx.resource_access];
    return fields.every((v) => (v || "unknown") === "unknown");
  }, [ctx]);
  return (
    <SkeletonPage
      title="Your Career Results"
      subtitle="Top recommendations based on your assessment."
    >
      <div className="cp-results">
        <div className="cp-resultsActions">
          <Button variant="secondary" onClick={() => navigate("/student/dashboard")}>
            Back to Dashboard
          </Button>

          <Button onClick={() => navigate("/student/results/history")}>
            View History
          </Button>

          <Button variant="secondary" disabled>
            Download Report
          </Button>
        </div>

        {loading && <p>Loading results…</p>}

        {!loading && error && <ResultsNotReadyView content={resultsNotReady_v1} />}

        {!loading && !error && (
          <>
            {/* Context */}
            <div className="results-section">
              <div className="results-section__titleRow">
                <div>
                  <div className="results-section__title">Your context (optional)</div>

                  {isContextUnknown ? (
                    <div className="text-muted results-section__sub">
                      Optional details that help us interpret results more fairly. You can change this anytime.
                    </div>
                  ) : (
                    <div className="text-muted results-section__sub">
                      We use this only to adjust assumptions, not to judge you.
                    </div>
                  )}
                </div>

                <Button variant="secondary" onClick={() => navigate("/student/context")}>
                  <span className="cp-inlineIcon">
                    <PencilIcon />
                    {isContextUnknown ? "Add" : "Edit"}
                  </span>
                </Button>
              </div>

              <div className="card cp-sectionCard">
                <div className="cp-contextGrid">
                  <div className="cp-miniCard">
                    <div className="cp-miniLabel text-muted">Education board</div>
                    <div className="cp-miniValue">{labelOrNotShared(ctx?.education_board)}</div>
                  </div>

                  <div className="cp-miniCard">
                    <div className="cp-miniLabel text-muted">Support level</div>
                    <div className="cp-miniValue">{labelOrNotShared(ctx?.support_level)}</div>
                  </div>

                  <div className="cp-miniCard">
                    <div className="cp-miniLabel text-muted">Resource access</div>
                    <div className="cp-miniValue">{labelOrNotShared(ctx?.resource_access)}</div>
                  </div>

                  <div className="cp-miniCard">
                    <div className="cp-miniLabel text-muted">SES band</div>
                    <div className="cp-miniValue">{labelOrNotShared(ctx?.ses_band)}</div>
                  </div>
                </div>

                <div className="cp-contextExplain">
                  <details className="cp-details">
                    <summary className="cp-detailsSummary">
                      {getContextImpactCopyV1({ ctx }).title}
                    </summary>

                    <div className="text-muted cp-detailsBody">
                      <div style={{ marginBottom: 8 }}>
                        {getContextImpactCopyV1({ ctx }).intro}
                      </div>

                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {getContextImpactCopyV1({ ctx }).bullets.map((line, idx) => (
                          <li key={idx} style={{ marginBottom: 6 }}>
                            {line}
                          </li>
                        ))}
                      </ul>

                      <div style={{ marginTop: 8 }}>
                        {getContextImpactCopyV1({ ctx }).footer}{" "}
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={() => navigate("/student/context")}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") navigate("/student/context");
                          }}
                          className="cp-linkButton"
                        >
                          Context
                        </span>
                        .
                      </div>
                    </div>
                  </details>
                </div>
              </div>
            </div>

            {/* Latest Assessment */}
            <div className="results-section">
              <div className="results-section__titleRow">
                <div>
                  <div className="results-section__title">Latest Assessment</div>
                  <div className="text-muted results-section__sub">
                    A summary of the most recent assessment used for these results.
                  </div>
                </div>
              </div>

              <div className="card" style={{ padding: 12 }}>
                <p>
                  You have completed <strong>{data?.total_results ?? 0}</strong> assessment(s).
                </p>

                {selectedResult ? (
                  <>
                    <p>
                      Showing result for <strong>your latest assessment</strong>
                    </p>

                    <p>
                      Generated on{" "}
                      <strong>
                        {selectedResult.generated_at
                          ? new Date(selectedResult.generated_at).toLocaleString()
                          : "Just now"}
                      </strong>
                    </p>

                    {(() => {
                      const copy = getResultsBlocksV1({ result: selectedResult });
                      const rec = copy.recommendations;
                      const fitBandsCopy = copy.fitBands || {};
                      const assoc = copy.associatedQualities || null;

                      const renderTopCareersCards = () => {
                        const topBlock = backendBlocks.find((b) => b?.block_type === "TOP_CAREERS");
                        const items = Array.isArray(topBlock?.items)
                          ? topBlock.items
                          : selectedResult.top_careers || [];

                        if (!items || items.length === 0) {
                          return (
                            <div className="text-muted" style={{ padding: 12 }}>
                              No recommendations available yet.
                            </div>
                          );
                        }

                        return (
                          <div className="cp-cards3">
                            {items.slice(0, 3).map((c, idx) => (
                              <TopCareerCard
                                key={c.career_id || c.career_code || c.career_title || idx}
                                career={c}
                                fitBandsCopy={fitBandsCopy}
                                idx={idx}
                              />
                            ))}
                          </div>
                        );
                      };

                      const renderPremiumInsightsCard = () => {
                        if (!assoc) return null;

                        const resolvedFacets = (Array.isArray(explainRes?.facets) ? explainRes.facets : [])
                          .filter((t) => typeof t === "string" && t.trim().length > 0)
                          // Safety: never show raw facet keys if backend returns them as text
                          .filter((t) => !/^AQ\d{2}_F\d$/i.test(t.trim()));

                        const resolvedAqs = (Array.isArray(explainRes?.aqs) ? explainRes.aqs : [])
                          .filter((t) => typeof t === "string" && t.trim().length > 0)
                          // Safety: never show raw AQ keys if backend returns them as text
                          .filter((t) => !/^AQ_\d{2}$/i.test(t.trim()));

                        const qualitiesBody = explainLoading ? (
                          <div className="text-muted" style={{ fontSize: 13 }}>
                            Loading qualities…
                          </div>
                        ) : resolvedAqs.length > 0 ? (
                          <ul style={{ marginTop: 10, paddingLeft: 18 }}>
                            {resolvedAqs.map((q, idx) => (
                              <li key={idx} style={{ marginBottom: 8 }}>
                                {q}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <div className="text-muted" style={{ fontSize: 13 }}>
                            {"Insights coming soon."}
                          </div>
                        );

                        const themesBody = explainLoading ? (
                          <div className="text-muted" style={{ fontSize: 13 }}>
                            Loading themes…
                          </div>
                        ) : resolvedFacets.length > 0 ? (
                          <ul style={{ marginTop: 10, paddingLeft: 18 }}>
                            {resolvedFacets.map((t, idx) => (
                              <li key={idx} style={{ marginBottom: 8 }}>
                                {t}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <div className="text-muted" style={{ fontSize: 13 }}>
                            {"Insights coming soon."}
                          </div>
                        );
                                                
                        return (
                          <div style={{ marginTop: 14 }}>
                            <div className="text-muted" style={{ fontSize: 12, marginBottom: 8 }}>
                              Premium insights
                            </div>

                            <div className="cp-insights2">
                              <div className="cp-softPanel">
                                <div style={{ fontWeight: 700, marginBottom: 6 }}>Focus themes</div>
                                {themesBody}
                                {explainError ? (
                                  <div className="text-muted" style={{ fontSize: 12, marginTop: 8 }}>
                                    {explainError}
                                  </div>
                                ) : null}
                              </div>

                              <div className="cp-softPanel">
                                <div style={{ fontWeight: 700, marginBottom: 6 }}>
                                  Associated qualities
                                </div>

                                 {explainLoading || resolvedAqs.length > 0 ? (
                                   <details>
                                     <summary style={{ cursor: "pointer", fontWeight: 600 }}>
                                       View qualities
                                     </summary>

                                     {qualitiesBody}

                                     <div className="text-muted" style={{ fontSize: 12, marginTop: 10 }}>
                                       Premium will include deeper “why this fits you” stories and guided next steps.
                                     </div>
                                   </details>
                                 ) : (
                                   <div className="text-muted" style={{ fontSize: 13 }}>
                                     {"Insights coming soon."}
                                   </div>
                                 )}
                              </div>
                            </div>
                          </div>
                        );
                      };

                      return (
                        <div className="results-section" style={{ marginTop: 10 }}>
                          <div className="results-section__titleRow">
                            <div>
                              <div className="results-section__title">{rec.title}</div>
                              <div className="text-muted results-section__sub">
                                Your top matches are shown using student-safe fit bands (no scores).
                              </div>
                            </div>
                          </div>

                          <div className="card" style={{ padding: 16 }}>
                            <div style={{ marginBottom: 14 }}>
                              <div className="text-muted" style={{ fontSize: 12, marginBottom: 4 }}>
                                Recommended stream
                              </div>
                              <div style={{ fontWeight: 700 }}>
                                {selectedResult.recommended_stream || "—"}
                              </div>
                            </div>

                            {renderTopCareersCards()}

                            {(resultsTier === "paid" || resultsTier === "premium") &&
                              renderPremiumInsightsCard()}
                          </div>

                          <style>{`
                            .cp-results { display: flex; flex-direction: column; gap: 16px; }
                            .cp-resultsActions { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
                            .results-section { margin-top: 6px; }
                            .results-section__titleRow { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
                            .results-section__title { font-size: 16px; font-weight: 800; line-height: 1.2; }
                            .results-section__sub { font-size: 13px; line-height: 1.45; }
                            .cp-sectionCard { padding: 16px; }
                            .cp-inlineIcon { display: inline-flex; align-items: center; gap: 8px; }
                            .cp-contextGrid { margin-top: 2px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
                            .cp-miniCard { border: 1px solid rgba(0,0,0,0.08); border-radius: 12px; padding: 12px; }
                            .cp-miniLabel { font-size: 12px; margin-bottom: 4px; }
                            .cp-miniValue { font-weight: 700; line-height: 1.25; }
                            .cp-contextExplain { margin-top: 12px; }
                            .cp-detailsSummary { cursor: pointer; font-weight: 700; }
                            .cp-detailsBody { font-size: 13px; margin-top: 10px; line-height: 1.5; }
                            .cp-linkButton { text-decoration: underline; cursor: pointer; }
                            .cp-cards3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; align-items: stretch; }
                            .cp-insights2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: stretch; }
                            .cp-softPanel { border: 1px solid rgba(0,0,0,0.08); border-radius: 12px; padding: 14px; background: rgba(0,0,0,0.02); }
                            .top-career-card { padding: 16px; border-radius: 14px; }
                            .top-career-card__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
                            .top-career-card__titleWrap { min-width: 0; }
                            .top-career-card__title { font-weight: 800; line-height: 1.2; }
                            .top-career-card__cluster { font-size: 12px; margin-top: 4px; }
                            .top-career-card__bandPill { font-size: 12px; font-weight: 700; border: 1px solid rgba(0,0,0,0.12); border-radius: 999px; padding: 6px 10px; white-space: nowrap; }
                            .top-career-card__bandDesc { font-size: 13px; line-height: 1.45; margin-bottom: 10px; }
                            .top-career-card__drivers { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.45; }
                            .top-career-card__drivers li { margin-bottom: 6px; }
                            @media (max-width: 980px) {
                              .cp-contextGrid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                              .cp-cards3 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                              .cp-insights2 { grid-template-columns: 1fr; }
                            }
                            @media (max-width: 560px) {
                              .cp-contextGrid { grid-template-columns: 1fr; }
                              .cp-cards3 { grid-template-columns: 1fr; }
                            }
                          `}</style>
                        </div>
                      );
                    })()}
                  </>
                ) : (
                  <ResultsNotReadyView content={resultsNotReady_v1} />
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </SkeletonPage>
  );
}

