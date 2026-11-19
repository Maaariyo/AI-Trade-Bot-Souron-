// The eight screens from SPEC section 8, with the phase that builds each one.

export type Screen = {
  href: string;
  label: string;
  phase: string;
  summary: string;
};

export const SCREENS: readonly Screen[] = [
  {
    href: "/",
    label: "Dashboard",
    phase: "Phase 6",
    summary:
      "Nifty 50 and Nifty 500, a sector heatmap, today's verdicts by conviction, watchlist changes and alerts.",
  },
  {
    href: "/screener",
    label: "Screener",
    phase: "Phase 2",
    summary: "Every stock with its composite score, factor percentiles and gates passed.",
  },
  {
    href: "/weights",
    label: "Weights",
    phase: "Phase 2",
    summary: "Factor sliders, presets, gates and agent weights, with a live top-20 preview.",
  },
  {
    href: "/runs",
    label: "Runs",
    phase: "Phase 6",
    summary: "The council queue: status per round, tokens, searches, cost and served model.",
  },
  {
    href: "/track-record",
    label: "Track record",
    phase: "Phase 7",
    summary: "Council IC against the factor screen on the same dates, by action band, with ablations.",
  },
  {
    href: "/audit",
    label: "Audit",
    phase: "Phase 6",
    summary: "Read-only audit log: pack and prompt hashes, models, raw outputs, verifier labels.",
  },
  {
    href: "/settings",
    label: "Settings",
    phase: "Phase 6",
    summary: "Connect Kite, schedules, budget caps, the kill switch and the mode.",
  },
] as const;

export const STOCK_SCREEN: Screen = {
  href: "/stock/[isin]",
  label: "Stock Council",
  phase: "Phase 5",
  summary: "One stock: the verdict card, seven assessments, the debate and the evidence.",
};

export function screenFor(href: string): Screen {
  const screen = SCREENS.find((s) => s.href === href);
  if (!screen) throw new Error(`Unknown screen: ${href}`);
  return screen;
}
