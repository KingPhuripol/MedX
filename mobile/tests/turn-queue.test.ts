/** T4–T5 turn posting: completed only, once per key, commit order, reconcile-then-retry, timestamps (C7, C16). */
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Reply } from "@/lib/api";
import { splitText, TurnQueue, type TurnBody } from "@/lib/turnQueue";

type R = { ok: true };
type Script = (Reply<R> | "hang")[];

const ok = (): Reply<R> => ({ status: 200, data: { ok: true }, body: {}, retryAfterMs: null });
const st = (status: number): Reply<R> => ({ status, data: null, body: {}, retryAfterMs: null });

function make(script: Script = [], stored: { text: string; started_at: string }[] = []) {
  const posts: { body: TurnBody; at: number }[] = [];
  const failed: string[] = [];
  const fatal: string[] = [];
  const reconciled: TurnBody[] = [];
  let gets = 0;
  const q = new TurnQueue<R, unknown>({
    post: async (body) => {
      posts.push({ body, at: Date.now() });
      const r = script.shift() ?? ok();
      if (r === "hang") return new Promise(() => undefined);
      return r;
    },
    fetchSession: async () => {
      gets += 1;
      return { turns: stored, data: {} };
    },
    onPosted: () => undefined,
    onReconciled: (b) => reconciled.push(b),
    onFatal: (k) => fatal.push(k),
    onFailed: (k) => failed.push(k),
    asrModel: () => "fixture-transcribe",
    now: () => Date.now(),
  });
  return { q, posts, failed, fatal, reconciled, gets: () => gets };
}

const texts = (p: { body: TurnBody }[]) => p.map((x) => x.body.text);
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$/;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-30T10:30:00+07:00"));
});

describe("TurnQueue", () => {
  it("delta-like activity (speech/commit only) posts nothing; completed posts exactly one exact body", async () => {
    const t = make();
    t.q.speechStarted("a");
    await vi.advanceTimersByTimeAsync(1200);
    t.q.speechStopped("a");
    t.q.committed("a");
    await vi.advanceTimersByTimeAsync(100);
    expect(t.posts).toHaveLength(0);
    t.q.completed("a", "  ปวดท้องค่ะ.  ");
    await vi.advanceTimersByTimeAsync(0);
    expect(t.posts).toHaveLength(1);
    const b = t.posts[0].body;
    expect(Object.keys(b).sort()).toEqual(["asr_model", "ended_at", "source", "speaker", "started_at", "text"]);
    expect(b).toMatchObject({ speaker: "unknown", text: "ปวดท้องค่ะ", source: "asr", asr_model: "fixture-transcribe" });
    expect(b.started_at).toMatch(ISO);
    expect(b.ended_at).toMatch(ISO);
    expect(Date.parse(b.ended_at) - Date.parse(b.started_at)).toBe(1200);
    expect(Date.parse(b.ended_at)).toBeLessThanOrEqual(t.posts[0].at);
  });

  it("ignores a duplicate completed for the same item", async () => {
    const t = make();
    t.q.committed("a");
    expect(t.q.completed("a", "หนึ่ง")).toBe(true);
    expect(t.q.completed("a", "หนึ่ง")).toBe(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(texts(t.posts)).toEqual(["หนึ่ง"]);
  });

  it("posts out-of-order completions in commit order", async () => {
    const t = make();
    t.q.committed("a");
    t.q.committed("b");
    t.q.committed("c");
    t.q.completed("c", "สาม");
    t.q.completed("b", "สอง");
    await vi.advanceTimersByTimeAsync(0);
    expect(t.posts).toHaveLength(0);
    t.q.completed("a", "หนึ่ง");
    await vi.advanceTimersByTimeAsync(0);
    expect(texts(t.posts)).toEqual(["หนึ่ง", "สอง", "สาม"]);
  });

  it("a failed item releases the queue and is counted, never posted", async () => {
    const t = make();
    t.q.committed("a");
    t.q.committed("b");
    t.q.completed("b", "สอง");
    t.q.failed("a");
    t.q.completed("a", "late");
    await vi.advanceTimersByTimeAsync(0);
    expect(texts(t.posts)).toEqual(["สอง"]);
    expect(t.failed).toEqual(["a"]);
  });

  it("skips an earlier item stuck for 15 s without fabricating text", async () => {
    const t = make();
    t.q.committed("a");
    t.q.committed("b");
    t.q.completed("b", "สอง");
    await vi.advanceTimersByTimeAsync(14_900);
    expect(t.posts).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(200);
    expect(texts(t.posts)).toEqual(["สอง"]);
    expect(t.failed).toEqual(["a"]);
    t.q.completed("a", "late text");
    await vi.advanceTimersByTimeAsync(0);
    expect(t.posts).toHaveLength(1);
  });

  it("completed with no prior commit is appended in completion order", async () => {
    const t = make();
    t.q.completed("x", "เอ็กซ์");
    t.q.completed("y", "วาย");
    await vi.advanceTimersByTimeAsync(0);
    expect(texts(t.posts)).toEqual(["เอ็กซ์", "วาย"]);
  });

  it("splits a transcript over 2,000 chars at whitespace into ordered parts", async () => {
    const word = "ก".repeat(99);
    const long = Array.from({ length: 30 }, () => word).join(" "); // 2,999 chars
    expect(splitText(long).every((p) => p.length <= 2000)).toBe(true);
    expect(splitText(long).join(" ")).toBe(long);
    const t = make();
    t.q.completed("big", long);
    await vi.advanceTimersByTimeAsync(0);
    expect(t.posts).toHaveLength(2);
    expect(t.q.wasPosted("big#1") && t.q.wasPosted("big#2")).toBe(true);
    expect(t.posts.map((p) => p.body.text).join(" ")).toBe(long);
  });

  it("does not post empty text after normalising", async () => {
    const t = make();
    t.q.completed("s", " … ");
    await vi.advanceTimersByTimeAsync(0);
    expect(t.posts).toHaveLength(0);
  });

  it("one POST in flight at a time", async () => {
    const t = make(["hang"]);
    t.q.completed("a", "หนึ่ง");
    t.q.completed("b", "สอง");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(texts(t.posts)).toEqual(["หนึ่ง"]);
  });

  it("started_at is non-decreasing across the session and ended_at never precedes it", async () => {
    const t = make();
    t.q.speechStarted("a");
    await vi.advanceTimersByTimeAsync(3000);
    t.q.speechStarted("b");
    t.q.speechStopped("b");
    t.q.speechStopped("a");
    t.q.committed("a");
    t.q.committed("b");
    t.q.completed("b", "สอง");
    t.q.completed("a", "หนึ่ง");
    await vi.advanceTimersByTimeAsync(0);
    const starts = t.posts.map((p) => Date.parse(p.body.started_at));
    expect(starts[1]).toBeGreaterThanOrEqual(starts[0]);
    for (const p of t.posts) {
      expect(Date.parse(p.body.ended_at)).toBeGreaterThanOrEqual(Date.parse(p.body.started_at));
      expect(Date.parse(p.body.ended_at)).toBeLessThanOrEqual(p.at);
    }
  });

  it("missing speech times fall back to the committed time", async () => {
    const t = make();
    t.q.committed("a");
    const commitAt = Date.now();
    await vi.advanceTimersByTimeAsync(500);
    t.q.completed("a", "หนึ่ง");
    await vi.advanceTimersByTimeAsync(0);
    expect(Date.parse(t.posts[0].body.started_at)).toBe(commitAt);
    expect(Date.parse(t.posts[0].body.ended_at)).toBe(commitAt);
  });
});

describe("T5 turn POST failures", () => {
  it("401 stops the queue and reports auth", async () => {
    const t = make([st(401)]);
    t.q.completed("a", "หนึ่ง");
    t.q.completed("b", "สอง");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(t.fatal).toEqual(["auth"]);
    expect(t.posts).toHaveLength(1);
  });

  it("409 stops with inactive and never retries", async () => {
    const t = make([st(409)]);
    t.q.completed("a", "หนึ่ง");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(t.fatal).toEqual(["inactive"]);
    expect(t.posts).toHaveLength(1);
    expect(t.gets()).toBe(0);
  });

  it("422 drops the item as failed without retry and moves on", async () => {
    const t = make([st(422)]);
    t.q.completed("a", "หนึ่ง");
    t.q.completed("b", "สอง");
    await vi.advanceTimersByTimeAsync(0);
    expect(texts(t.posts)).toEqual(["หนึ่ง", "สอง"]);
    expect(t.failed).toEqual(["a"]);
  });

  it("5xx: GET reconcile, then retries at 1 s and 3 s, then counts failed", async () => {
    const t = make([st(502), st(503), st(500)]);
    t.q.completed("a", "หนึ่ง");
    await vi.advanceTimersByTimeAsync(0);
    expect(t.posts).toHaveLength(1);
    expect(t.gets()).toBe(1);
    await vi.advanceTimersByTimeAsync(999);
    expect(t.posts).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(t.posts).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(3000);
    expect(t.posts).toHaveLength(3);
    expect(t.gets()).toBe(3);
    expect(t.failed).toEqual(["a"]);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(t.posts).toHaveLength(3);
  });

  it("network error where the turn was already stored posts 0 extra (ambiguous failure)", async () => {
    const stored: { text: string; started_at: string }[] = [];
    const t = make([st(0)], stored);
    t.q.committed("a");
    t.q.completed("a", "หนึ่ง");
    // The server stored it before the connection dropped: GET shows the same text and started_at.
    stored.push({ text: "หนึ่ง", started_at: new Date(Date.now()).toISOString() });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(t.posts).toHaveLength(1);
    expect(t.reconciled).toHaveLength(1);
    expect(t.q.wasPosted("a")).toBe(true);
    expect(t.failed).toEqual([]);
  });

  it("network error where the turn is not stored retries and succeeds once", async () => {
    const t = make([st(0), ok()]);
    t.q.completed("a", "หนึ่ง");
    await vi.advanceTimersByTimeAsync(1000);
    expect(t.posts).toHaveLength(2);
    expect(t.q.wasPosted("a")).toBe(true);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(t.posts).toHaveLength(2);
  });

  it("stop() (after finish) posts nothing further", async () => {
    const t = make();
    t.q.stop();
    t.q.completed("a", "หนึ่ง");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(t.posts).toHaveLength(0);
  });
});
