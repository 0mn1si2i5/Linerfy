import { describe, expect, it } from "vitest";

import {
  nowPlayingRequestSchema,
  releaseSlug,
  requestFingerprint,
  type NowPlayingRequest,
} from "./request";

function np(overrides: Partial<NowPlayingRequest> = {}): NowPlayingRequest {
  return {
    provider: "spotify",
    title: "Mariners Apartment Complex",
    artist: "Lana Del Rey",
    album: "Norman Fucking Rockwell!",
    state: "playing",
    ...overrides,
  };
}

describe("nowPlayingRequestSchema", () => {
  it("accepts a minimal spotify request", () => {
    const parsed = nowPlayingRequestSchema.safeParse({
      provider: "spotify",
      title: "Mariners Apartment Complex",
      artist: "Lana Del Rey",
      album: "Norman Fucking Rockwell!",
    });
    expect(parsed.success).toBe(true);
  });

  it("defaults state to playing", () => {
    const parsed = nowPlayingRequestSchema.parse({
      provider: "apple-music",
      title: "t",
      artist: "a",
      album: "b",
    });
    expect(parsed.state).toBe("playing");
  });

  it("rejects an unknown provider", () => {
    const parsed = nowPlayingRequestSchema.safeParse({
      provider: "youtube",
      title: "t",
      artist: "a",
      album: "b",
    });
    expect(parsed.success).toBe(false);
  });
});

describe("requestFingerprint", () => {
  it("is stable across whitespace and case", () => {
    const a = requestFingerprint(
      np({ artist: " Lana   Del Rey ", album: "Norman Fucking Rockwell!" }),
    );
    const b = requestFingerprint(
      np({ artist: "lana del rey", album: "norman   fucking rockwell!" }),
    );
    expect(a).toBe(b);
  });

  it("prefers the provider URL over artist/album", () => {
    const withUrl = requestFingerprint(np({ providerUrl: "spotify:track:123" }));
    const withoutUrl = requestFingerprint(np());
    expect(withUrl).not.toBe(withoutUrl);
  });

  it("separates different albums", () => {
    const a = requestFingerprint(np({ album: "Norman Fucking Rockwell!" }));
    const b = requestFingerprint(np({ album: "Chemtrails Over the Country Club" }));
    expect(a).not.toBe(b);
  });
});

describe("releaseSlug", () => {
  it("slugifies artist and album", () => {
    expect(releaseSlug("Lana Del Rey", "Norman Fucking Rockwell!")).toBe(
      "lana-del-rey-norman-fucking-rockwell",
    );
  });

  it("falls back to unknown for empty parts", () => {
    expect(releaseSlug("!!!", "   ")).toBe("unknown-unknown");
  });
});
