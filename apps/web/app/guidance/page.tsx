import { connection } from "next/server";
import { Suspense } from "react";

import { apiGet } from "@/lib/api";

import { ReviewForm } from "./review-form";

type Row = {
  id: number;
  isin: string;
  method: string;
  stated_on: string;
  metric: string;
  metric_detail: string | null;
  target_period: string;
  target_low_stated: string;
  target_high_stated: string;
  unit_stated: string;
  quote: string;
  page_no: number | null;
  status: string;
  flag: string | null;
  review_note: string | null;
};

type Stats = {
  by_status: Record<string, number>;
  verified_reviewed: number;
  agreement: number | null;
};

// Rows Agent 7 may use (CLAUDE.md rule 10).
const USABLE = new Set(["QUOTE_VERIFIED", "HUMAN_REVIEWED"]);

const UNIT: Record<string, string> = {
  percent: "%",
  inr_crore: " cr",
  inr_lakh: " lakh",
  inr: " Rs",
  times: "x",
};

function target(r: Row): string {
  const unit = UNIT[r.unit_stated] ?? "";
  const low = Number(r.target_low_stated);
  const high = Number(r.target_high_stated);
  return low === high ? `${low}${unit}` : `${low}-${high}${unit}`;
}

async function Rows() {
  await connection();
  const [rows, stats] = await Promise.all([
    apiGet<Row[]>("/guidance"),
    apiGet<Stats>("/guidance/stats"),
  ]);
  if (rows === null)
    return <p className="text-sm text-down">▼ The API is unreachable.</p>;
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted">
        No guidance rows yet. Load a transcript, then run the extraction
        (docs/DATA.md).
      </p>
    );
  }
  const agreement =
    stats?.agreement == null
      ? "no quote-verified rows reviewed yet"
      : `${(stats.agreement * 100).toFixed(1)}% of ${stats.verified_reviewed} reviewed quote-verified rows approved`;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        Agreement: {agreement}. The Phase 1b bar is 90% over 50 reviewed rows.
      </p>
      <ul className="space-y-3">
        {rows.map((r) => (
          <li
            key={r.id}
            className="space-y-2 rounded-md border border-line p-3"
          >
            <div className="flex flex-wrap items-baseline gap-x-3 text-sm">
              <span className="font-mono">{r.isin}</span>
              <span className="font-medium">
                {r.metric_detail || r.metric} {target(r)} for {r.target_period}
              </span>
              <span className="text-muted">
                stated {r.stated_on}
                {r.page_no ? `, page ${r.page_no}` : ""} · {r.method}
              </span>
              <span className={USABLE.has(r.status) ? "text-up" : "text-down"}>
                {USABLE.has(r.status) ? "▲" : "▼"} {r.status}
              </span>
            </div>
            <blockquote className="border-l-2 border-line pl-3 text-sm">
              {r.quote}
            </blockquote>
            {r.flag && <p className="text-xs text-down">Flag: {r.flag}</p>}
            {r.review_note && (
              <p className="text-xs text-muted">Note: {r.review_note}</p>
            )}
            {(r.status === "EXTRACTED" || r.status === "QUOTE_VERIFIED") && (
              <ReviewForm id={r.id} flagged={Boolean(r.flag)} />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function GuidancePage() {
  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Guidance review
        </h1>
        <p className="text-muted">
          Management targets extracted from transcripts. Agent 7 uses only
          quote-verified or approved rows. Flagged rows failed the code check
          and need your decision.
        </p>
      </header>
      <Suspense
        fallback={<p className="text-sm text-muted">Loading guidance rows…</p>}
      >
        <Rows />
      </Suspense>
    </section>
  );
}
