/** V2C-C15 client: finish exactly once before submitReview, 409 = done, only 2xx is success, TODO(v2d) marker. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { submitFlow, type ReviewPayload } from "@/lib/review";

import { installApi } from "./helpers";

const payload: ReviewPayload = {
  session_id: "vs_1",
  patient_ref: "SYN-2026-0023",
  decisions: [],
  consent_acknowledged_at: "2026-09-30T10:28:00.000+07:00",
  red_flag_acknowledged_at: null,
};

function run(finish: number, review: number | "network") {
  const api = installApi({
    on: {
      "/api/voice/sessions/vs_1/finish": () => ({ status: finish, body: {} }),
      "/api/voice/sessions/vs_1/review": () => (review === "network" ? "network" : { status: review, body: {} }),
    },
  });
  return { api, p: submitFlow("vs_1", payload) };
}

describe("submitFlow", () => {
  it.each([
    [200, 200, "submitted"],
    [200, 201, "submitted"],
    [409, 200, "submitted"],
    [200, 404, "not_connected"],
    [200, 405, "not_connected"],
    [200, 501, "not_connected"],
    [200, 500, "error"],
    [200, 422, "error"],
    [200, "network", "error"],
    [500, 200, "error"],
    [401, 200, "auth"],
    [200, 401, "auth"],
  ] as const)("finish %s, review %s → %s", async (finish, review, outcome) => {
    const { api, p } = run(finish, review);
    const r = await p;
    expect(r.outcome).toBe(outcome);
    const paths = api.calls.map((c) => `${c.method} ${c.url}`);
    expect(paths.filter((x) => x.endsWith("/finish"))).toHaveLength(1);
    expect(paths[0]).toBe("POST /api/voice/sessions/vs_1/finish");
    if (finish === 200 || finish === 409) {
      expect(paths[1]).toBe("POST /api/voice/sessions/vs_1/review");
      expect(api.calls[1].body).toEqual(payload);
      expect(r.finished).toBe(true);
    } else {
      expect(paths).toHaveLength(1);
      expect(r.finished).toBe(false);
    }
  });

  it("review.ts carries the TODO(v2d) marker on the submit fetch", () => {
    expect(readFileSync(resolve(__dirname, "../lib/review.ts"), "utf8")).toContain("// TODO(v2d): endpoint and body owned by slice v2d");
  });
});
