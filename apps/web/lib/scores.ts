// Types shared by the Screener and Weights Studio (mirrors services/api/scores.py).

export type ScoreRow = {
  isin: string;
  name: string;
  nse_symbol: string | null;
  industry: string | null;
  sector: string | null;
  passed: boolean;
  reasons: string[];
  composite: number | null;
  coverage: number | null;
  thin_data: boolean;
  rank: number | null;
  family_scores: Record<string, number>;
};

export type ScoresOut = {
  run_id: number;
  as_of: string;
  weights: Record<string, number>;
  unavailable_factors: string[];
  rows: ScoreRow[];
};

export type Gates = {
  min_median_value_crore: number;
  min_mcap_crore: number;
  min_quarters: number;
  exclude_gsm: boolean;
  exclude_asm: boolean;
};

export type PresetsOut = {
  families: string[];
  presets: Record<string, Record<string, number>>;
  default: string;
  gates: Gates;
  agent_weights: Record<string, number>;
  coverage_min: number;
};

export type Profile = {
  name: string;
  family_weights: Record<string, number>;
  gates: Gates;
  agent_weights: Record<string, number>;
};

export type PreviewRow = {
  rank: number;
  isin: string;
  nse_symbol: string | null;
  name: string;
  composite: number;
  move: number | null;
};

export type PreviewOut = {
  run_id: number;
  as_of: string;
  passed: number;
  ranked: number;
  thin_data: number;
  unavailable_factors: string[];
  elapsed_ms: number;
  top: PreviewRow[];
};

export const FAMILY_LABEL: Record<string, string> = {
  value: "Value",
  quality: "Quality",
  growth: "Growth",
  momentum: "Momentum",
  risk: "Risk",
  ownership: "Ownership",
  governance: "Governance",
};
