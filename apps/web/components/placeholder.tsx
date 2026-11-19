import type { ReactNode } from "react";

import type { Screen } from "@/lib/routes";

export function Placeholder({ screen, children }: { screen: Screen; children?: ReactNode }) {
  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{screen.label}</h1>
        <p className="text-muted">{screen.summary}</p>
      </header>
      <p className="rounded-md border border-line px-3 py-2 text-sm text-muted">
        Not built yet. This screen arrives in {screen.phase} (docs/SPEC.md section 11).
      </p>
      {children}
    </section>
  );
}
