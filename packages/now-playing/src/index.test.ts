import { describe, expect, it, vi } from "vitest";

import {
  APPLE_MUSIC_NOW_PLAYING_SCRIPT,
  SPOTIFY_NOW_PLAYING_SCRIPT,
  createAppleMusicProvider,
  createNowPlayingService,
  createSpotifyProvider,
  type NowPlayingTrack,
} from "./index";

const spotifyTrack = {
  provider: "spotify",
  title: "Maroon",
  artist: "Taylor Swift",
  album: "Midnights",
  providerUrl: "spotify:track:example",
} satisfies NowPlayingTrack;

describe("now-playing providers", () => {
  it("runs a fixed Spotify program and parses its JSON result", async () => {
    const scriptRunner = vi.fn(async () => JSON.stringify(spotifyTrack));
    const provider = createSpotifyProvider(scriptRunner);

    await expect(provider.getNowPlaying()).resolves.toEqual(spotifyTrack);
    expect(scriptRunner).toHaveBeenCalledWith(SPOTIFY_NOW_PLAYING_SCRIPT);
  });

  it("returns null for a stopped Apple Music app", async () => {
    const scriptRunner = vi.fn(async () => "null\n");

    await expect(
      createAppleMusicProvider(scriptRunner).getNowPlaying(),
    ).resolves.toBeNull();
    expect(scriptRunner).toHaveBeenCalledWith(APPLE_MUSIC_NOW_PLAYING_SCRIPT);
  });

  it("uses the first active provider and tolerates an unavailable app", async () => {
    const unavailable = {
      getNowPlaying: vi.fn(async () => Promise.reject(new Error("closed"))),
    };
    const active = { getNowPlaying: vi.fn(async () => spotifyTrack) };

    await expect(
      createNowPlayingService([unavailable, active]).getNowPlaying(),
    ).resolves.toEqual(spotifyTrack);
  });
});
