"use server";

import { apiSend } from "@/lib/api";
import type { Gates, PreviewOut } from "@/lib/scores";

export type PreviewInput = {
  family_weights: Record<string, number>;
  gates: Gates;
  baseline_weights: Record<string, number> | null;
};

export async function previewAction(
  input: PreviewInput,
): Promise<{ data: PreviewOut | null; error: string | null }> {
  const res = await apiSend<PreviewOut>("POST", "/scores/preview", {
    ...input,
    top: 20,
  });
  return res.ok
    ? { data: res.data, error: null }
    : { data: null, error: res.detail };
}

export async function saveProfileAction(
  name: string,
  profile: {
    family_weights: Record<string, number>;
    gates: Gates;
    agent_weights: Record<string, number>;
  },
): Promise<string | null> {
  const clean = name.trim();
  if (!clean) return "Give the profile a name.";
  const res = await apiSend<null>(
    "PUT",
    `/profiles/${encodeURIComponent(clean)}`,
    profile,
  );
  return res.ok ? null : res.detail;
}

export async function runScreenAction(): Promise<string | null> {
  const res = await apiSend<unknown>("POST", "/screen/run", {});
  return res.ok ? null : res.detail;
}
