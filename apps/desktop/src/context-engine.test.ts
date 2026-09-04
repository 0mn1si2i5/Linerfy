import { featuredContext } from "@linerfy/domain/fixtures";
import type { NowPlayingTrack } from "@linerfy/now-playing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ContextEngine,
  type ContextEngineOptions,
  type FetchOutcome,
} from "./context-engine";
import type { ContextState } from "./context-state";

function track(overrides: Partial<NowPlayingTrack> = {}): NowPlayingTrack {
  return {
    provider: "spotify",
    title: "Song",
    artist: "Artist",
    album: "Album",
    state: "playing",
    ...overrides,
  };
}

const trackA = track({ album: "Album A" });
const trackB = track({ album: "Album B" });

function deferred() {
  let resolve!: (outcome: FetchOutcome) => void;
  const promise = new Promise<FetchOutcome>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

interface Harness {
  engine: ContextEngine;
  fetch: ReturnType<typeof vi.fn>;
  send: ReturnType<typeof vi.fn>;
  resolve: (index: number, outcome: FetchOutcome) => Promise<void>;
}

function setup(options: Partial<ContextEngineOptions> = {}): Harness {
  const pending: Array<ReturnType<typeof deferred>> = [];
  const fetch = vi.fn((_track: NowPlayingTrack, _signal: AbortSignal) => {
    const d = deferred();
    pending.push(d);
    return d.promise;
  });
  const send = vi.fn();
  const engine = new ContextEngine({
    fetch,
    send,
    pollIntervalMs: 2500,
    requestTimeoutMs: 15_000,
    maxRetries: 3,
    ...options,
  });
  return {
    engine,
    fetch,
    send,
    resolve: async (index, outcome) => {
      pending[index]!.resolve(outcome);
      // Let the awaiting fetchOnce continuation run to completion.
      for (let i = 0; i < 4; i++) await Promise.resolve();
    },
  };
}

function statuses(send: ReturnType<typeof vi.fn>): string[] {
  return send.mock.calls.map((call) => (call[0] as ContextState).status);
}

const ready = (): FetchOutcome => ({
  status: "ok",
  body: { status: "ready", context: featuredContext },
});
const partial = (): FetchOutcome => ({
  status: "ok",
  body: {
    status: "partial",
    stage: "build_consensus",
    context: featuredContext,
  },
});

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("ContextEngine", () => {
  it("issues at most one request for the same track", () => {
    const { engine, fetch } = setup();
    engine.onTrack(trackA);
    engine.onTrack(trackA);
    engine.onTrack(trackA);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not supersede a slow request for the same track", async () => {
    const { engine, fetch, send, resolve } = setup();
    engine.onTrack(trackA);
    // A later now-playing poll for the same track must not start a second request.
    engine.onTrack(trackA);
    expect(fetch).toHaveBeenCalledTimes(1);
    await resolve(0, ready());
    expect(statuses(send)).toEqual(["loading", "ready"]);
  });

  it("drops a stale response after a track change", async () => {
    const { engine, fetch, send, resolve } = setup();
    engine.onTrack(trackA);
    engine.onTrack(trackB);
    expect(fetch).toHaveBeenCalledTimes(2);
    // The old track's response arrives late and must not overwrite the new one.
    await resolve(0, ready());
    expect(statuses(send)).toEqual(["loading", "loading"]);
    await resolve(1, ready());
    expect(statuses(send)).toEqual(["loading", "loading", "ready"]);
  });

  it("keeps polling after partial and stops after ready", async () => {
    const { engine, fetch, send, resolve } = setup();
    engine.onTrack(trackA);
    await resolve(0, partial());
    expect(statuses(send)).toEqual(["loading", "partial"]);

    vi.advanceTimersByTime(2500);
    expect(fetch).toHaveBeenCalledTimes(2);
    await resolve(1, ready());
    expect(statuses(send)).toEqual(["loading", "partial", "ready"]);

    // `ready` is terminal: no further timer fires.
    vi.advanceTimersByTime(10_000);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("stops after a terminal state", async () => {
    const { engine, fetch, send, resolve } = setup();
    engine.onTrack(trackA);
    await resolve(0, { status: "ok", body: { status: "unavailable" } });
    expect(statuses(send)).toEqual(["loading", "unavailable"]);
    vi.advanceTimersByTime(10_000);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("retries network errors a bounded number of times then surfaces an error", async () => {
    const { engine, fetch, send, resolve } = setup();
    engine.onTrack(trackA);
    await resolve(0, { status: "network-error" });
    vi.advanceTimersByTime(2500);
    await resolve(1, { status: "network-error" });
    vi.advanceTimersByTime(2500);
    await resolve(2, { status: "network-error" });
    vi.advanceTimersByTime(2500);
    await resolve(3, { status: "network-error" });

    // 1 initial + 3 retries, then an error state and no more polling.
    expect(fetch).toHaveBeenCalledTimes(4);
    expect(statuses(send)).toEqual(["loading", "error"]);
    vi.advanceTimersByTime(10_000);
    expect(fetch).toHaveBeenCalledTimes(4);
  });

  it("keeps partial content instead of replacing it with an error", async () => {
    const { engine, fetch, send, resolve } = setup();
    engine.onTrack(trackA);
    await resolve(0, partial());
    // All subsequent polls fail; partial must not be cleared.
    for (let i = 1; i <= 4; i++) {
      vi.advanceTimersByTime(2500);
      await resolve(i, { status: "network-error" });
    }
    expect(statuses(send)).toEqual(["loading", "partial"]);
    expect(fetch).toHaveBeenCalledTimes(5); // initial + 4 (one initial + maxRetries)
  });

  it("aborts the in-flight request when the track changes", async () => {
    const { engine, fetch } = setup();
    engine.onTrack(trackA);
    engine.onTrack(trackB);
    // The first request's signal is aborted so the transport can stop it.
    expect(fetch).toHaveBeenCalledTimes(2);
    const firstSignal = fetch.mock.calls[0]![1] as AbortSignal;
    expect(firstSignal.aborted).toBe(true);
  });
});
