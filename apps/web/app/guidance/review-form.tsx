"use client";

import { useActionState } from "react";

import { reviewAction, type ReviewState } from "./actions";

export function ReviewForm({ id, flagged }: { id: number; flagged: boolean }) {
  const [state, action, pending] = useActionState<ReviewState, FormData>(
    reviewAction,
    {
      error: null,
    },
  );
  return (
    <form action={action} className="space-y-1">
      <div className="flex flex-wrap gap-2">
        <input type="hidden" name="id" value={id} />
        <input
          name="note"
          aria-label="Review note"
          placeholder={
            flagged
              ? "Note (required to approve a flagged row)"
              : "Note (optional)"
          }
          className="min-w-0 flex-1 rounded border border-line bg-transparent px-2 py-1 text-sm"
        />
        <button
          name="decision"
          value="approve"
          disabled={pending}
          className="rounded border border-line px-3 py-1 text-sm text-up disabled:opacity-50"
        >
          ▲ Approve
        </button>
        <button
          name="decision"
          value="reject"
          disabled={pending}
          className="rounded border border-line px-3 py-1 text-sm text-down disabled:opacity-50"
        >
          ▼ Reject
        </button>
      </div>
      {state.error && (
        <p role="alert" className="text-xs text-down">
          {state.error}
        </p>
      )}
    </form>
  );
}
