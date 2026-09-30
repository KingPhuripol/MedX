/**
 * Turn posting (SPEC §11 T4–T5): completed items only, exactly once per key, in commit order,
 * one POST in flight, across every reconnect of one voice session.
 */
import type { Reply } from "./api";
import { normaliseTranscript } from "./realtime";
import { isoWithOffset } from "./time";

export const MAX_TEXT = 2000;
export const STUCK_MS = 15000;
export const RETRY_DELAYS_MS = [1000, 3000] as const;

export interface TurnBody {
  speaker: "unknown";
  text: string;
  started_at: string;
  ended_at: string;
  source: "asr";
  asr_model: string;
}

export interface QueueHooks<R, G> {
  post(body: TurnBody): Promise<Reply<R>>;
  /** GET the session; `null` when the GET itself failed. */
  fetchSession(): Promise<{ turns: { text: string; started_at: string }[]; data: G } | null>;
  onPosted(body: TurnBody, resp: R): void;
  /** A retried post turned out to be stored already; `data` is the GET payload. */
  onReconciled(body: TurnBody, data: G): void;
  onFatal(kind: "auth" | "inactive"): void;
  onFailed(key: string): void;
  asrModel(): string;
  now(): number;
}

interface Entry {
  id: string;
  completed: boolean;
  text: string;
  commitMs?: number;
  blockSince?: number;
}

/** Split a long transcript at whitespace into ordered parts of at most `max` characters. */
export function splitText(text: string, max = MAX_TEXT): string[] {
  const parts: string[] = [];
  let rest = text.trim();
  while (rest.length > max) {
    let cut = rest.lastIndexOf(" ", max);
    if (cut <= 0) cut = max;
    parts.push(rest.slice(0, cut).trim());
    rest = rest.slice(cut).trim();
  }
  if (rest) parts.push(rest);
  return parts;
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export class TurnQueue<R = unknown, G = unknown> {
  private order: Entry[] = [];
  private entries = new Map<string, Entry>();
  /** Item ids already accepted as completed, failed or skipped: never posted again. */
  private final = new Set<string>();
  private postedKeys = new Set<string>();
  /** Keys already counted failed: never posted again, even after restart(). */
  private failedKeys = new Set<string>();
  private times = new Map<string, { start?: number; end?: number }>();
  private busy = false;
  private stopped = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private lastStart = 0;
  private lastEnd = 0;
  private idleWaiters: (() => void)[] = [];

  constructor(private hooks: QueueHooks<R, G>) {}

  speechStarted(id: string) {
    const t = this.times.get(id) ?? {};
    t.start ??= this.hooks.now();
    this.times.set(id, t);
  }

  speechStopped(id: string) {
    const t = this.times.get(id) ?? {};
    t.end = this.hooks.now();
    this.times.set(id, t);
  }

  committed(id: string) {
    if (this.final.has(id) || this.entries.has(id)) return;
    const e: Entry = { id, completed: false, text: "", commitMs: this.hooks.now() };
    this.entries.set(id, e);
    this.order.push(e);
  }

  /** Returns false when the event is a duplicate or arrives for an item already finalised. */
  completed(id: string, transcript: string): boolean {
    if (this.final.has(id)) return false;
    this.final.add(id);
    let e = this.entries.get(id);
    if (!e) {
      e = { id, completed: false, text: "" };
      this.entries.set(id, e);
      this.order.push(e); // completed with no prior commit: completion order
    }
    e.completed = true;
    e.text = normaliseTranscript(transcript);
    void this.pump();
    return true;
  }

  failed(id: string) {
    if (this.final.has(id)) return;
    this.final.add(id);
    this.drop(id);
    this.hooks.onFailed(id);
    void this.pump();
  }

  /** On connection close: items committed but not completed will never complete; release the queue. */
  dropPending() {
    for (const e of [...this.order]) {
      if (!e.completed) {
        this.final.add(e.id);
        this.drop(e.id);
        this.hooks.onFailed(e.id);
      }
    }
    void this.pump();
  }

  /** Items committed but not yet completed (speech still being transcribed). */
  pendingCompletions(): number {
    return this.order.filter((e) => !e.completed).length;
  }

  isIdle(): boolean {
    return !this.busy && this.order.length === 0;
  }

  /** Resolve when every completed item is posted and nothing waits (or after `timeoutMs`). */
  waitIdle(timeoutMs: number): Promise<void> {
    if (this.isIdle()) return Promise.resolve();
    return new Promise((resolve) => {
      const t = setTimeout(done, timeoutMs);
      const waiter = () => done();
      this.idleWaiters.push(waiter);
      const self = this;
      function done() {
        clearTimeout(t);
        self.idleWaiters = self.idleWaiters.filter((w) => w !== waiter);
        resolve();
      }
    });
  }

  /** After `finish`: nothing is ever posted again. */
  stop() {
    this.stopped = true;
    clearTimeout(this.timer);
  }

  restart() {
    this.stopped = false;
    void this.pump();
  }

  wasPosted(key: string): boolean {
    return this.postedKeys.has(key);
  }

  private drop(id: string) {
    this.order = this.order.filter((e) => e.id !== id);
    this.entries.delete(id);
  }

  private notifyIdle() {
    if (!this.isIdle()) return;
    for (const w of [...this.idleWaiters]) w();
  }

  private arm(ms: number) {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.pump(), ms);
  }

  private async pump(): Promise<void> {
    if (this.busy || this.stopped) return;
    this.busy = true;
    try {
      while (!this.stopped && this.order.length) {
        const head = this.order[0];
        if (!head.completed) {
          if (!this.order.some((e) => e.completed)) break;
          const now = this.hooks.now();
          head.blockSince ??= now;
          const left = STUCK_MS - (now - head.blockSince);
          if (left > 0) {
            this.arm(left);
            break;
          }
          // Stuck for 15 s behind a completed item: skip it, never fabricate its text.
          this.final.add(head.id);
          this.drop(head.id);
          this.hooks.onFailed(head.id);
          continue;
        }
        this.order.shift();
        this.entries.delete(head.id);
        const parts = splitText(head.text);
        for (let i = 0; i < parts.length; i++) {
          const key = parts.length > 1 ? `${head.id}#${i + 1}` : head.id;
          if (this.postedKeys.has(key) || this.failedKeys.has(key)) continue;
          const ok = await this.send(key, this.body(head, parts[i]));
          if (ok === "fatal") return;
          if (ok === "stopped") {
            // Stopped before this part was sent: hold the item at the head for restart().
            this.entries.set(head.id, head);
            this.order.unshift(head);
            return;
          }
        }
        this.times.delete(head.id);
      }
    } finally {
      this.busy = false;
    }
    this.notifyIdle();
  }

  private body(e: Entry, text: string): TurnBody {
    const now = this.hooks.now();
    const t = this.times.get(e.id) ?? {};
    let start = t.start ?? e.commitMs ?? now;
    let end = t.end ?? e.commitMs ?? now;
    start = Math.max(start, this.lastStart, this.lastEnd);
    end = Math.min(Math.max(end, start), now);
    start = Math.min(start, end);
    return {
      speaker: "unknown",
      text,
      started_at: isoWithOffset(start),
      ended_at: isoWithOffset(end),
      source: "asr",
      asr_model: this.hooks.asrModel(),
    };
  }

  private accept(key: string, body: TurnBody) {
    this.postedKeys.add(key);
    this.lastStart = Date.parse(body.started_at);
    this.lastEnd = Date.parse(body.ended_at);
  }

  private fail(key: string): "failed" {
    this.failedKeys.add(key);
    this.hooks.onFailed(key);
    return "failed";
  }

  /** T5. Returns "posted", "failed", "fatal" or "stopped" (nothing sent; caller holds the item). */
  private async send(key: string, body: TurnBody): Promise<"posted" | "failed" | "fatal" | "stopped"> {
    if (!body.text) return "failed"; // empty after normalising (silence): nothing to post, not a lost segment
    for (let attempt = 0; ; attempt++) {
      if (this.stopped) {
        if (attempt === 0) return "stopped";
        // T5 × T9 (SPEC §17 option A): finish cut off a failing POST that reconcile did not find stored.
        // Count it failed exactly once; it is never posted again.
        return this.fail(key);
      }
      const r = await this.hooks.post(body);
      if (r.data) {
        this.accept(key, body);
        this.hooks.onPosted(body, r.data);
        return "posted";
      }
      if (r.status === 401 || r.status === 409) {
        this.stop();
        this.hooks.onFatal(r.status === 401 ? "auth" : "inactive");
        return "fatal";
      }
      if (r.status === 422 || (r.status >= 400 && r.status < 500 && r.status !== 408 && r.status !== 429)) {
        return this.fail(key);
      }
      // Network error, timeout or 5xx: the turn may already be stored. Reconcile before any retry.
      const got = await this.hooks.fetchSession();
      if (got?.turns.some((t) => t.text === body.text && Date.parse(t.started_at) === Date.parse(body.started_at))) {
        this.accept(key, body);
        this.hooks.onReconciled(body, got.data);
        return "posted";
      }
      if (attempt >= RETRY_DELAYS_MS.length) return this.fail(key);
      await sleep(RETRY_DELAYS_MS[attempt]);
    }
  }
}
