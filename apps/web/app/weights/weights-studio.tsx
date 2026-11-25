"use client";

import { useEffect, useRef, useState, useTransition } from "react";

import {
  FAMILY_LABEL,
  type Gates,
  type PresetsOut,
  type PreviewOut,
  type Profile,
} from "@/lib/scores";

import { previewAction, runScreenAction, saveProfileAction } from "./actions";

const AGENT_LABEL: Record<string, string> = {
  deep_reasoner: "Deep",
  news_catalyst: "News",
  company_peers: "Company",
  industry_macro: "Industry",
  management_governance: "Mgmt",
  risk_on: "Risk-On",
  capital_preserver: "Preserver",
};
const ADVOCATES = new Set(["risk_on", "capital_preserver"]);

function sameWeights(
  a: Record<string, number>,
  b: Record<string, number>,
): boolean {
  return Object.keys(a).every((k) => a[k] === b[k]);
}

export function WeightsStudio({
  presets,
  profiles,
}: {
  presets: PresetsOut;
  profiles: Profile[];
}) {
  const [weights, setWeights] = useState(presets.presets[presets.default]);
  const [baseline, setBaseline] = useState(presets.presets[presets.default]);
  const [gates, setGates] = useState<Gates>(presets.gates);
  const [agents, setAgents] = useState(presets.agent_weights);
  const [preview, setPreview] = useState<PreviewOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [roundTrip, setRoundTrip] = useState<number | null>(null);
  const [profileName, setProfileName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const requestId = useRef(0);

  const presetName =
    Object.entries(presets.presets).find(([, w]) =>
      sameWeights(w, weights),
    )?.[0] ?? "Custom";

  useEffect(() => {
    const id = ++requestId.current;
    const timer = setTimeout(async () => {
      const started = performance.now();
      const res = await previewAction({
        family_weights: weights,
        gates,
        baseline_weights: baseline,
      });
      if (id !== requestId.current) return; // a newer slider position won
      setRoundTrip(performance.now() - started);
      setPreview(res.data);
      setError(res.error);
    }, 120);
    return () => clearTimeout(timer);
  }, [weights, gates, baseline]);

  function loadProfile(name: string) {
    const p = profiles.find((x) => x.name === name);
    if (!p) return;
    setWeights(p.family_weights);
    setBaseline(p.family_weights);
    setGates(p.gates);
    setAgents(p.agent_weights);
    setProfileName(p.name);
  }

  function save() {
    startTransition(async () => {
      const err = await saveProfileAction(profileName, {
        family_weights: weights,
        gates,
        agent_weights: agents,
      });
      setMessage(err ?? `Saved profile "${profileName.trim()}".`);
      if (!err) setBaseline(weights);
    });
  }

  function runScreen() {
    startTransition(async () => {
      const err = await runScreenAction();
      setMessage(
        err ?? "Screen run started. Reload in a minute to rank on the new run.",
      );
    });
  }

  const gateNumber = (key: keyof Gates, label: string, step = 1) => (
    <label className="flex items-center justify-between gap-3">
      <span className="text-muted">{label}</span>
      <input
        type="number"
        min={0}
        step={step}
        value={Number(gates[key])}
        onChange={(e) => setGates({ ...gates, [key]: Number(e.target.value) })}
        className="w-24 rounded border border-line bg-transparent px-2 py-0.5 text-right"
      />
    </label>
  );

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-5">
        <div className="flex flex-wrap gap-2 text-sm">
          {[...Object.keys(presets.presets), "Custom"].map((name) => (
            <button
              key={name}
              type="button"
              disabled={name === "Custom"}
              onClick={() => setWeights(presets.presets[name])}
              className={`rounded border px-3 py-1 ${presetName === name ? "border-fg" : "border-line text-muted"}`}
            >
              {name}
            </button>
          ))}
          {profiles.length > 0 && (
            <select
              aria-label="Load a saved profile"
              defaultValue=""
              onChange={(e) => loadProfile(e.target.value)}
              className="rounded border border-line bg-bg px-2 py-1"
            >
              <option value="" disabled>
                Saved profiles
              </option>
              {profiles.map((p) => (
                <option key={p.name}>{p.name}</option>
              ))}
            </select>
          )}
        </div>

        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-medium uppercase tracking-wide text-muted">
            Factor weights (0-10)
          </legend>
          {presets.families.map((fam) => (
            <label
              key={fam}
              className="grid grid-cols-[7rem_1fr_2rem] items-center gap-3 text-sm"
            >
              <span>{FAMILY_LABEL[fam] ?? fam}</span>
              <input
                type="range"
                min={0}
                max={10}
                step={1}
                value={weights[fam]}
                aria-label={`${FAMILY_LABEL[fam] ?? fam} weight`}
                onChange={(e) =>
                  setWeights({ ...weights, [fam]: Number(e.target.value) })
                }
              />
              <span className="text-right tabular-nums">{weights[fam]}</span>
            </label>
          ))}
        </fieldset>

        <fieldset className="space-y-2 text-sm">
          <legend className="mb-2 font-medium uppercase tracking-wide text-muted">
            Gates
          </legend>
          {gateNumber(
            "min_median_value_crore",
            "Median traded value, Rs crore/day",
          )}
          {gateNumber("min_mcap_crore", "Market cap at least, Rs crore", 50)}
          {gateNumber("min_quarters", "Quarters of financials at least")}
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={gates.exclude_gsm}
              onChange={(e) =>
                setGates({ ...gates, exclude_gsm: e.target.checked })
              }
            />
            Exclude GSM
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={gates.exclude_asm}
              onChange={(e) =>
                setGates({ ...gates, exclude_asm: e.target.checked })
              }
            />
            Exclude ASM
          </label>
        </fieldset>

        <fieldset className="space-y-2 text-sm">
          <legend className="mb-2 font-medium uppercase tracking-wide text-muted">
            Agent weights (0-3)
          </legend>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.keys(agents).map((key) => (
              <label
                key={key}
                className="flex items-center justify-between gap-2"
              >
                <span className={ADVOCATES.has(key) ? "text-muted" : ""}>
                  {AGENT_LABEL[key] ?? key}
                </span>
                <input
                  type="number"
                  min={0}
                  max={3}
                  step={0.5}
                  value={agents[key]}
                  onChange={(e) =>
                    setAgents({ ...agents, [key]: Number(e.target.value) })
                  }
                  className="w-16 rounded border border-line bg-transparent px-1 py-0.5 text-right"
                />
              </label>
            ))}
          </div>
          <p className="text-xs text-muted">
            Used by the council from Phase 5. Advocates (greyed) vote only if
            decision D2 changes.
          </p>
        </fieldset>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <input
            aria-label="Profile name"
            placeholder="Profile name"
            value={profileName}
            onChange={(e) => setProfileName(e.target.value)}
            className="min-w-0 flex-1 rounded border border-line bg-transparent px-2 py-1"
          />
          <button
            type="button"
            onClick={save}
            disabled={pending}
            className="rounded border border-line px-3 py-1"
          >
            Save profile
          </button>
          <button
            type="button"
            onClick={runScreen}
            disabled={pending}
            className="rounded border border-line px-3 py-1"
          >
            Run screen
          </button>
        </div>
        {message && <p className="text-sm text-muted">{message}</p>}
      </div>

      <div className="space-y-2">
        <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
          Live preview: top 20
        </h2>
        {error && (
          <p role="alert" className="text-sm text-down">
            ▼ {error}
          </p>
        )}
        {preview && (
          <>
            <p className="text-xs text-muted">
              As of {preview.as_of}: {preview.passed} pass the gates,{" "}
              {preview.ranked} ranked, {preview.thin_data} thin data. Re-ranked
              in{" "}
              <span data-testid="roundtrip">
                {roundTrip === null ? "…" : Math.round(roundTrip)}
              </span>{" "}
              ms (server {Math.round(preview.elapsed_ms)} ms).
            </p>
            {preview.unavailable_factors.length > 0 && (
              <p className="text-xs text-down">
                ▼ No data yet for: {preview.unavailable_factors.join(", ")}
              </p>
            )}
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-muted">
                  <th className="px-2 py-1 font-normal">Rank</th>
                  <th className="px-2 py-1 font-normal">Stock</th>
                  <th className="px-2 py-1 text-right font-normal">Score</th>
                  <th className="px-2 py-1 text-right font-normal">Move</th>
                </tr>
              </thead>
              <tbody>
                {preview.top.map((r) => (
                  <tr key={r.isin} className="border-b border-line/50">
                    <td className="px-2 py-1 tabular-nums">{r.rank}</td>
                    <td className="px-2 py-1">
                      {r.nse_symbol ?? r.isin}{" "}
                      <span className="text-xs text-muted">{r.name}</span>
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums">
                      {r.composite.toFixed(1)}
                    </td>
                    <td
                      className={`px-2 py-1 text-right tabular-nums ${
                        r.move === null
                          ? "text-muted"
                          : r.move > 0
                            ? "text-up"
                            : r.move < 0
                              ? "text-down"
                              : ""
                      }`}
                    >
                      {r.move === null
                        ? "new"
                        : r.move > 0
                          ? `▲ ${r.move}`
                          : r.move < 0
                            ? `▼ ${-r.move}`
                            : "0"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
