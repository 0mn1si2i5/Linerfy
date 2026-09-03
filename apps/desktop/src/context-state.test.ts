import type { NowPlayingTrack } from "@linerfy/now-playing";
import { describe, expect, it } from "vitest";

import { trackKey } from "./context-state";

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
