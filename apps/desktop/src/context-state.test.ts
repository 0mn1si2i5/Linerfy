import { featuredContext } from "@linerfy/domain/fixtures";
import type { NowPlayingTrack } from "@linerfy/now-playing";
import { describe, expect, it } from "vitest";

import * as contextState from "./context-state";

const { trackKey } = contextState;

function track(overrides: Partial<NowPlayingTrack> = {}): NowPlayingTrack {
  return {
    provider: "spotify",
    title: "Mariners Apartment Complex",
    artist: "Lana Del Rey",
    album: "Norman Fucking Rockwell!",
    state: "playing",
    ...overrides,
  };
}

describe("trackKey", () => {
  it("is stable for the same track", () => {
    expect(trackKey(track())).toBe(trackKey(track()));
  });

  it("changes when the album changes", () => {
    expect(
      trackKey(track({ album: "Chemtrails Over the Country Club" })),
    ).not.toBe(trackKey(track()));
  });

  it("changes when the provider URL changes", () => {
    expect(trackKey(track({ providerUrl: "spotify:track:1" }))).not.toBe(
      trackKey(track({ providerUrl: "spotify:track:2" })),
    );
  });
});

describe("contextStatusLabel", () => {
  it("shows only the login requirement while signed out", () => {
    const label = (
      contextState as typeof contextState & {
        contextStatusLabel: (
          authStatus: "signed-out" | "signed-in",
          context: { status: string },
        ) => string | null;
      }
    ).contextStatusLabel;

    expect(typeof label).toBe("function");
    expect(label?.("signed-out", { status: "loading" })).toBe("登录后加载乐评");
    expect(label?.("signed-out", { status: "queued" })).toBe("登录后加载乐评");
  });

  it("renders content while partial instead of a status label", () => {
    // A partial context is safe to show; the label must be null so the renderer
    // displays the context card (plus its "still filling in" note) rather than
    // a "loading" message. This is the polling-until-ready contract.
    const partial: contextState.ContextState = {
      status: "partial",
      context: featuredContext,
      stage: "build_consensus",
    };

    expect(contextState.contextStatusLabel("signed-in", partial)).toBeNull();
  });
});

describe("parseContextApiResponse", () => {
  it("accepts a partial response with a context", () => {
    const parsed = contextState.parseContextApiResponse({
      status: "partial",
      context: featuredContext,
      stage: "build_source_summaries",
    });

    expect(parsed.status).toBe("partial");
  });

  it("rejects a ready response that omits its context", () => {
    expect(() =>
      contextState.parseContextApiResponse({ status: "ready" }),
    ).toThrow();
  });
});
