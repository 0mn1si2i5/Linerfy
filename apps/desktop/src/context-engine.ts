import type { NowPlayingTrack } from "@linerfy/now-playing";

import {
  trackKey,
  type ContextApiResponse,
  type ContextState,
} from "./context-state";

/**
 * The outcome of one POST /api/context attempt, already narrowed by the caller.
 *
 * The engine never touches Electron or the network directly: the caller supplies
 * `fetch` (session + HTTP + schema validation) and `send` (IPC to the renderer),
 * so the timing/racing logic here stays testable without an Electron harness.
 */
export type FetchOutcome =
  | { status: "ok"; body: ContextApiResponse }
  | { status: "network-error" }
  | { status: "invalid" }
  | { status: "unauthorized" };

export type ContextFetch = (
  track: NowPlayingTrack,
  signal: AbortSignal,
) => Promise<FetchOutcome>;

export interface ContextEngineOptions {
  fetch: ContextFetch;
  send: (state: ContextState) => void;
  pollIntervalMs: number;
  requestTimeoutMs: number;
  maxRetries: number;
}

/**
 * The context status poll, kept separate from the now-playing poll.
 *
 * Invariants it guarantees:
 * - At most one request per track is in flight; a slow request is never
 *   superseded by another request for the *same* track.
 * - A track change invalidates the previous request (bumping a generation) and,
 *   because `fetch` receives an AbortSignal, actively aborts it.
 * - `queued`/`running`/`partial` schedule the next status request on a dedicated
 *   timer; `ready` and the terminal states stop it.
 * - Network errors retry a bounded number of times; once `partial` content has
 *   been shown it is never cleared by a later failure.
 */
export class ContextEngine {
  private readonly fetch: ContextFetch;
  private readonly send: (state: ContextState) => void;
  private readonly pollIntervalMs: number;
  private readonly requestTimeoutMs: number;
  private readonly maxRetries: number;

  private generation = 0;
  private activeTrackKey: string | null = null;
  private inFlight = false;
  private currentAbort: AbortController | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private retries = 0;
  private hadContent = false;

  constructor(options: ContextEngineOptions) {
    this.fetch = options.fetch;
    this.send = options.send;
    this.pollIntervalMs = options.pollIntervalMs;
    this.requestTimeoutMs = options.requestTimeoutMs;
    this.maxRetries = options.maxRetries;
  }

  /** Called on every now-playing poll; no-ops unless the track actually changed. */
  onTrack(track: NowPlayingTrack | null): void {
    const key = track ? trackKey(track) : null;
    if (key === this.activeTrackKey) return;
    this.reset();
    this.activeTrackKey = key;
    if (!track) {
      this.send({ status: "idle" });
      return;
    }
    this.send({ status: "loading" });
    void this.fetchOnce(track);
  }

  /** Tear everything down (sign-out, window hidden, quit). */
  stop(): void {
    this.reset();
  }

  private reset(): void {
    this.generation += 1;
    this.clearTimer();
    this.currentAbort?.abort();
    this.currentAbort = null;
    this.activeTrackKey = null;
    this.inFlight = false;
    this.retries = 0;
    this.hadContent = false;
  }

  private clearTimer(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private schedulePoll(track: NowPlayingTrack): void {
    this.clearTimer();
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.fetchOnce(track);
    }, this.pollIntervalMs);
  }

  private async fetchOnce(track: NowPlayingTrack): Promise<void> {
    if (this.inFlight) return;
    const generation = this.generation;
    this.inFlight = true;

    const controller = new AbortController();
    this.currentAbort = controller;
    const timeout = setTimeout(() => controller.abort(), this.requestTimeoutMs);

    let outcome: FetchOutcome;
    try {
      outcome = await this.fetch(track, controller.signal);
    } catch {
      outcome = { status: "network-error" };
    } finally {
      clearTimeout(timeout);
    }

    if (generation !== this.generation) {
      // Invalidated while in flight (track change or stop()). Leave `inFlight`
      // alone: a newer request may already own it.
      return;
    }
    this.inFlight = false;
    this.currentAbort = null;

    if (outcome.status === "unauthorized") {
      this.send({ status: "idle" });
      return;
    }
    if (outcome.status === "network-error") {
      this.handleNetworkError(track);
      return;
    }
    if (outcome.status === "invalid") {
      this.send({ status: "error", message: "响应格式错误" });
      return;
    }
    this.handleBody(track, outcome.body);
  }

  private handleNetworkError(track: NowPlayingTrack): void {
    this.retries += 1;
    if (this.retries <= this.maxRetries) {
      this.schedulePoll(track);
      return;
    }
    this.retries = 0;
    if (!this.hadContent) {
      this.send({ status: "error", message: "网络错误" });
    }
    // Partial content, once shown, is kept rather than replaced by an error.
  }

  private handleBody(track: NowPlayingTrack, body: ContextApiResponse): void {
    this.retries = 0;
    switch (body.status) {
      case "ready":
        this.hadContent = true;
        this.send({ status: "ready", context: body.context });
        return;
      case "partial":
        this.hadContent = true;
        this.send({
          status: "partial",
          context: body.context,
          stage: body.stage ?? "",
          paused: body.paused,
        });
        this.schedulePoll(track);
        return;
      case "queued":
      case "running":
        this.send({
          status: body.status,
          stage: body.stage ?? "",
          paused: body.paused,
        });
        this.schedulePoll(track);
        return;
      case "unavailable":
        this.send({ status: "unavailable" });
        return;
      case "ambiguous":
        this.send({ status: "ambiguous" });
        return;
      case "failed":
        this.send({ status: "failed" });
        return;
    }
  }
}
