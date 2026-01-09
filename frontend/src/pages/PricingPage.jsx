//CareerPlatform\frontend\src\pages\PricingPage.jsx

// src/pages/PricingPage.jsx
import React from "react";
import { Link } from "react-router-dom";
import PublicHeader from "../ui/PublicHeader";

function PriceCard({
  title,
  price,
  subtitle,
  features = [],
  ctaLabel,
  ctaTo,
  highlight = false,
}) {
  return (
    <div
      className={[
        "rounded-2xl border p-6 text-left shadow-sm",
        highlight ? "border-black" : "border-gray-200",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-gray-600">{subtitle}</p>
        </div>

        {highlight ? (
          <span className="rounded-full bg-black px-3 py-1 text-xs font-medium text-white">
            Recommended
          </span>
        ) : null}
      </div>

      <div className="mt-5">
        <div className="text-4xl font-semibold">{price}</div>
        <div className="mt-1 text-sm text-gray-600">per assessment</div>
      </div>

      <ul className="mt-5 space-y-2 text-sm">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2">
            <span className="mt-0.5 inline-block h-2 w-2 rounded-full bg-black" />
            <span>{f}</span>
          </li>
        ))}
      </ul>

      <div className="mt-6">
        <Link
          to={ctaTo}
          className={[
            "inline-flex w-full items-center justify-center rounded-xl px-4 py-3 text-sm font-medium",
            highlight
              ? "bg-black text-white hover:opacity-90"
              : "bg-gray-100 text-black hover:bg-gray-200",
          ].join(" ")}
        >
          {ctaLabel}
        </Link>

        <p className="mt-3 text-xs text-gray-500">
          No backend payment wiring in this step — CTA routes to existing flows.
        </p>
      </div>
    </div>
  );
}

export default function PricingPage() {
  return (
    <div>
      <PublicHeader />

      <div className="mx-auto max-w-5xl px-4 py-8">
        <header className="text-center">
          <h1 className="text-3xl font-semibold">Pricing</h1>
          <p className="mx-auto mt-3 max-w-2xl text-sm text-gray-600">
            CareerPlatform offers a deterministic, explainable assessment with a
            Free report and an upgraded Premium report.
          </p>
        </header>

        <section className="mt-10 grid gap-6 md:grid-cols-2">
          <PriceCard
            title="Free"
            price="£0"
            subtitle="Great for first-time exploration"
            features={[
              "Top recommended careers (basic)",
              "Core strengths summary",
              "Deterministic mapping (skills → careers)",
              "Shareable report link (UI-only for now)",
            ]}
            ctaLabel="Start with Free"
            ctaTo="/login"
          />

          <PriceCard
            title="Premium"
            price="£19"
            subtitle="Deeper analytics + explainability"
            highlight
            features={[
              "Cluster-level insights & key skill breakdown",
              "Explainable career fit (why these careers)",
              "More detailed report sections",
              "Designed for auditability & stability",
            ]}
            ctaLabel="Get Premium"
            ctaTo="/login"
          />
        </section>

        <section className="mt-10 rounded-2xl border border-gray-200 p-6 text-left">
          <h2 className="text-lg font-semibold">What you get</h2>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <div className="rounded-xl bg-gray-50 p-4">
              <div className="text-sm font-medium">Deterministic</div>
              <p className="mt-1 text-sm text-gray-600">
                Recommendations come from controlled mappings and scoring — not
                random outputs.
              </p>
            </div>
            <div className="rounded-xl bg-gray-50 p-4">
              <div className="text-sm font-medium">Explainable</div>
              <p className="mt-1 text-sm text-gray-600">
                Premium focuses on “why” — key skills and cluster drivers.
              </p>
            </div>
            <div className="rounded-xl bg-gray-50 p-4">
              <div className="text-sm font-medium">Compliance-first</div>
              <p className="mt-1 text-sm text-gray-600">
                Guardian consent gating remains enforced for minors in protected
                student routes.
              </p>
            </div>
            <div className="rounded-xl bg-gray-50 p-4">
              <div className="text-sm font-medium">Incremental build</div>
              <p className="mt-1 text-sm text-gray-600">
                This page is UI-only and safe to merge without backend changes.
              </p>
            </div>
          </div>

          <div className="mt-6 text-center">
            <p className="text-xs text-gray-500">
              Next step (later): connect Premium CTA to real checkout/payment and
              route to premium report pages.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
