import { describe, expect, it } from "vitest";

import {
  nowPlayingRequestSchema,
  releaseSlug,
  requestFingerprint,
  toIngestPayload,
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

  it("deduplicates tracks from the same album", () => {
    const firstTrack = requestFingerprint(
      np({ title: "Track 1", providerUrl: "spotify:track:1" }),
    );
    const secondTrack = requestFingerprint(
      np({ title: "Track 2", providerUrl: "spotify:track:2" }),
    );
    expect(firstTrack).toBe(secondTrack);
  });

  it("separates different albums", () => {
    const a = requestFingerprint(np({ album: "Norman Fucking Rockwell!" }));
    const b = requestFingerprint(
      np({ album: "Chemtrails Over the Country Club" }),
    );
    expect(a).not.toBe(b);
  });

  it("does not collide across a field that contains the separator", () => {
    // artist "a:b" / album "c" must not equal artist "a" / album "b:c".
    const left = requestFingerprint(np({ artist: "a:b", album: "c" }));
    const right = requestFingerprint(np({ artist: "a", album: "b:c" }));
    expect(left).not.toBe(right);
  });

  it("keeps distinct non-ASCII albums distinct", () => {
    const jay = requestFingerprint(np({ artist: "周杰伦", album: "范特西" }));
    const faye = requestFingerprint(np({ artist: "王菲", album: "寓言" }));
    expect(jay).not.toBe(faye);
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

  it("never collapses distinct non-ASCII names onto one slug", () => {
    const jay = releaseSlug("周杰伦", "范特西");
    const faye = releaseSlug("王菲", "寓言");
    // Pinned values shared with ingest/tests/test_pipeline.py: both ends produce
    // the identical slug, so the read path finds what the worker wrote.
    expect(jay).toBe("d1d51d7a7c5c-a23acf6103d1");
    expect(faye).toBe("b7e62df3267a-114fcb616f84");
    expect(jay).not.toBe(faye);
    expect(jay).not.toBe("unknown-unknown");
  });

  it("keeps distinct accented names distinct", () => {
    expect(releaseSlug("Björk", "Homogenic")).not.toBe(
      releaseSlug("Bjork", "Homogenic"),
    );
  });
});

describe("toIngestPayload", () => {
  it("maps providerUrl to the snake_case ingest contract", () => {
    const payload = toIngestPayload(np({ providerUrl: "spotify:track:123" }));
    expect(payload.provider_url).toBe("spotify:track:123");
    expect(payload).not.toHaveProperty("providerUrl");
  });

  it("omits provider_url when absent", () => {
    const payload = toIngestPayload(np());
    expect(payload).not.toHaveProperty("provider_url");
    expect(payload).toMatchObject({
      provider: "spotify",
      title: "Mariners Apartment Complex",
      artist: "Lana Del Rey",
      album: "Norman Fucking Rockwell!",
      state: "playing",
    });
  });
});
