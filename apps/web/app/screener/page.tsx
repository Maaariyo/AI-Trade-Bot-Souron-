import { connection } from "next/server";
import { Suspense } from "react";

import { apiGet } from "@/lib/api";
import type { ScoresOut } from "@/lib/scores";

import { ScreenerTable } from "./screener-table";

async function Universe() {
  await connection();
  const data = await apiGet<ScoresOut>("/scores");
  if (data === null) {
    return (
      <p className="text-sm text-muted">
        No screen run yet, or the API is unreachable. Load data (docs/DATA.md),
        then run <code>make screen</code>.
      </p>
    );
  }
  return <ScreenerTable data={data} />;
}

export default function ScreenerPage() {
  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Screener</h1>
        <p className="text-muted">
          Every stock with its composite score (0 to 100), family percentiles
          within its industry, and the gates it passed. Weights: Balanced
          preset; change them in Weights.
        </p>
      </header>
      <Suspense
        fallback={<p className="text-sm text-muted">Loading scores…</p>}
      >
        <Universe />
      </Suspense>
    </section>
  );
}
