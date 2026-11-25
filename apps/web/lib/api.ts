// Server-side helpers for calling the FastAPI service. Never import into client code.

export const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function apiGet<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export async function apiPost(
  path: string,
  body: unknown,
): Promise<{ ok: boolean; detail?: string }> {
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) return { ok: true };
    const data = (await res.json().catch(() => ({}))) as { detail?: string };
    return { ok: false, detail: data.detail ?? `HTTP ${res.status}` };
  } catch (err) {
    return {
      ok: false,
      detail: err instanceof Error ? err.message : "request failed",
    };
  }
}

export async function apiSend<T>(
  method: "POST" | "PUT",
  path: string,
  body: unknown,
): Promise<{ ok: true; data: T } | { ok: false; detail: string }> {
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method,
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { detail?: unknown };
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail ?? res.status);
      return { ok: false, detail };
    }
    const text = await res.text();
    return { ok: true, data: (text ? JSON.parse(text) : null) as T };
  } catch (err) {
    return {
      ok: false,
      detail: err instanceof Error ? err.message : "request failed",
    };
  }
}
