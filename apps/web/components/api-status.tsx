import { connection } from "next/server";

import { formatIST } from "@/lib/format";

type Health = {
  status: "ok" | "degraded";
  db: "ok" | "unavailable";
  worker_last_heartbeat: string | null;
  mode: "personal" | "publish";
  kill_switch: boolean;
};

const API_URL = process.env.API_URL ?? "http://localhost:8000";

async function fetchHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${API_URL}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    return res.ok ? ((await res.json()) as Health) : null;
  } catch {
    return null;
  }
}

/** Live system status. Render inside <Suspense>: it reads at request time. */
export async function ApiStatus() {
  await connection();
  const health = await fetchHealth();
  const rows: [string, string][] = health
    ? [
        ["API", health.status === "ok" ? "▲ ok" : "▼ degraded"],
        ["Database", health.db === "ok" ? "▲ ok" : "▼ unavailable"],
        [
          "Worker heartbeat",
          health.worker_last_heartbeat
            ? formatIST(new Date(health.worker_last_heartbeat))
            : "▼ none yet",
        ],
        ["Mode", health.mode],
        ["Kill switch", health.kill_switch ? "ON" : "off"],
      ]
    : [["API", `▼ unreachable at ${API_URL}`]];

  return (
    <dl className="grid max-w-md grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}
