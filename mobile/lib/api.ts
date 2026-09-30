/** Same-origin JSON calls to the backend (/api/* is rewritten by next.config.mjs). */

export interface Reply<T> {
  status: number; // 0 = network error or timeout
  data: T | null; // parsed body on 2xx only
  body: unknown; // parsed body on any status
  retryAfterMs: number | null;
}

export async function call<T>(url: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<Reply<T>> {
  const { timeoutMs = 15000, ...rest } = init;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const resp = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
      ...rest,
    });
    let body: unknown = null;
    try {
      body = await resp.json();
    } catch {
      /* empty body */
    }
    const ra = Number(resp.headers?.get?.("Retry-After"));
    return {
      status: resp.status,
      data: resp.ok ? (body as T) : null,
      body,
      retryAfterMs: Number.isFinite(ra) && ra > 0 ? ra * 1000 : null,
    };
  } catch {
    return { status: 0, data: null, body: null, retryAfterMs: null };
  } finally {
    clearTimeout(timer);
  }
}

export const post = <T>(url: string, json?: unknown, timeoutMs?: number) =>
  call<T>(url, { method: "POST", body: json === undefined ? undefined : JSON.stringify(json), timeoutMs });

export function reasonOf(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  const reason = (detail as { reason?: unknown } | null)?.reason ?? (body as { reason?: unknown } | null)?.reason;
  return typeof reason === "string" ? reason : null;
}
