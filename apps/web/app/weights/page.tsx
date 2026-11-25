import { connection } from "next/server";
import { Suspense } from "react";

import { apiGet } from "@/lib/api";
import type { PresetsOut, Profile } from "@/lib/scores";

import { WeightsStudio } from "./weights-studio";

async function Studio() {
  await connection();
  const [presets, profiles] = await Promise.all([
    apiGet<PresetsOut>("/presets"),
    apiGet<Profile[]>("/profiles"),
  ]);
  if (presets === null)
    return <p className="text-sm text-down">▼ The API is unreachable.</p>;
  return <WeightsStudio presets={presets} profiles={profiles ?? []} />;
}

export default function WeightsPage() {
  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Weights Studio
        </h1>
        <p className="text-muted">
          Factor-family weights (0 to 10), hard gates and agent weights. The top
          20 re-ranks as you move a slider; &quot;move&quot; is the change
          against where you started.
        </p>
      </header>
      <Suspense
        fallback={<p className="text-sm text-muted">Loading presets…</p>}
      >
        <Studio />
      </Suspense>
    </section>
  );
}
