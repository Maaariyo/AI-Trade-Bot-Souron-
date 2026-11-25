"use server";

import { refresh } from "next/cache";

import { apiPost } from "@/lib/api";

export type ReviewState = { error: string | null };

export async function reviewAction(
  _prev: ReviewState,
  formData: FormData,
): Promise<ReviewState> {
  const id = Number(formData.get("id"));
  const decision = formData.get("decision");
  if (!Number.isInteger(id) || id <= 0) return { error: "Invalid row id." };
  if (decision !== "approve" && decision !== "reject")
    return { error: "Unknown decision." };
  const note = String(formData.get("note") ?? "").trim() || null;
  const result = await apiPost(`/guidance/${id}/${decision}`, { note });
  if (!result.ok)
    return { error: result.detail ?? "The API refused the change." };
  refresh();
  return { error: null };
}
