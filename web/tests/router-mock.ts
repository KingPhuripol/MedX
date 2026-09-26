import { vi } from "vitest";

export const router = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  redirect: vi.fn(),
}));

export function mockFetch(status: number, body: unknown = {}) {
  const fn = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}
