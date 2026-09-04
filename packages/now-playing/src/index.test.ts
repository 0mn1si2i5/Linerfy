import { describe, expect, it, vi } from "vitest";

import {
  APPLE_MUSIC_CONTROL_SCRIPTS,
  APPLE_MUSIC_NOW_PLAYING_SCRIPT,
  SPOTIFY_CONTROL_SCRIPTS,
  SPOTIFY_NOW_PLAYING_SCRIPT,
  SPOTIFY_SEEK_SCRIPT,
  createAppleMusicProvider,
  createNowPlayingService,
  createSpotifyProvider,
  type PlaybackAction,
  type NowPlayingTrack,
} from "./index";

const spotifyTrack = {
  provider: "spotify",
  title: "Maroon",
  artist: "Taylor Swift",
  album: "Midnights",
  state: "playing",
  providerUrl: "spotify:track:example",
  artworkUrl: "https://i.scdn.co/image/example",
  durationMs: 234_000,
  positionMs: 61_000,
} satisfies NowPlayingTrack;

const appleMusicTrack = {
  provider: "apple-music",
  title: "Maroon",
  artist: "Taylor Swift",
  album: "Midnights",
  state: "playing",
} satisfies NowPlayingTrack;

function provider(track: NowPlayingTrack | null) {
  return {
    providerName: track?.provider ?? "spotify",
    getNowPlaying: vi.fn(async () => track),
    control: vi.fn(async () => {}),
    seek: vi.fn(async () => {}),
  };
}

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

  it("rejects a provider result without a playback state", async () => {
    const scriptRunner = vi.fn(async () =>
      JSON.stringify({
        provider: "spotify",
        title: "x",
        artist: "y",
        album: "z",
      }),
    );

    await expect(
      createSpotifyProvider(scriptRunner).getNowPlaying(),
    ).rejects.toThrow("Invalid spotify now-playing result");
  });

  it("rejects artwork outside Spotify's image host", async () => {
    const scriptRunner = vi.fn(async () =>
      JSON.stringify({
        ...spotifyTrack,
        artworkUrl: "https://example.com/untrusted.png",
      }),
    );

    await expect(
      createSpotifyProvider(scriptRunner).getNowPlaying(),
    ).rejects.toThrow("Invalid spotify now-playing result");
  });

  it("tolerates an unavailable provider", async () => {
    const unavailable = {
      providerName: "spotify" as const,
      getNowPlaying: vi.fn(async () => Promise.reject(new Error("closed"))),
      control: vi.fn(async () => {}),
      seek: vi.fn(async () => {}),
    };
    const active = provider(spotifyTrack);

    await expect(
      createNowPlayingService([unavailable, active]).getNowPlaying(),
    ).resolves.toEqual(spotifyTrack);
  });
});

describe("now-playing provider conflict resolution", () => {
  it("prefers the playing provider over a paused one", async () => {
    const pausedSpotify = { ...spotifyTrack, state: "paused" as const };
    const playingApple = appleMusicTrack;

    const service = createNowPlayingService([
      provider(pausedSpotify),
      provider(playingApple),
    ]);

    await expect(service.getNowPlaying()).resolves.toEqual(playingApple);
  });

  it("keeps the recent provider when both are paused", async () => {
    const pausedSpotify = { ...spotifyTrack, state: "paused" as const };
    const pausedApple = { ...appleMusicTrack, state: "paused" as const };

    const service = createNowPlayingService([
      provider(pausedSpotify),
      provider(pausedApple),
    ]);

    // First call has no preference yet: the first provider wins.
    await expect(service.getNowPlaying()).resolves.toEqual(pausedSpotify);
    // Second call keeps the same provider (still paused, no playing signal).
    await expect(service.getNowPlaying()).resolves.toEqual(pausedSpotify);
  });

  it("overrides the recent preference when the other provider starts playing", async () => {
    const pausedSpotify = { ...spotifyTrack, state: "paused" as const };
    const pausedApple = { ...appleMusicTrack, state: "paused" as const };

    const spotifyProvider = provider(pausedSpotify);
    const appleProvider = provider(pausedApple);
    const service = createNowPlayingService([spotifyProvider, appleProvider]);

    await expect(service.getNowPlaying()).resolves.toEqual(pausedSpotify);

    // Apple Music starts playing: it must win over the paused preference.
    appleProvider.getNowPlaying.mockResolvedValue(appleMusicTrack);
    await expect(service.getNowPlaying()).resolves.toEqual(appleMusicTrack);
  });
});

describe("playback control and seek", () => {
  it("maps each transport action to its fixed Spotify program", async () => {
    const scriptRunner = vi.fn(async () => "");
    const provider = createSpotifyProvider(scriptRunner);

    for (const action of ["previous", "toggle", "next"] as const) {
      await provider.control(action);
      expect(scriptRunner).toHaveBeenLastCalledWith(
        SPOTIFY_CONTROL_SCRIPTS[action],
      );
    }
  });

  it("maps each transport action to its fixed Apple Music program", async () => {
    const scriptRunner = vi.fn(async () => "");
    const provider = createAppleMusicProvider(scriptRunner);

    const actions: PlaybackAction[] = ["previous", "toggle", "next"];
    for (const action of actions) {
      await provider.control(action);
      expect(scriptRunner).toHaveBeenLastCalledWith(
        APPLE_MUSIC_CONTROL_SCRIPTS[action],
      );
    }
  });

  it("passes the seek position as a separate argument, never interpolated", async () => {
    const scriptRunner = vi.fn(async () => "");
    const provider = createSpotifyProvider(scriptRunner);

    await provider.seek(61_000);

    // The program text is the fixed seek script; the position travels as
    // argv[0] in seconds, so it can never become part of the program string.
    expect(scriptRunner).toHaveBeenCalledWith(SPOTIFY_SEEK_SCRIPT, ["61"]);
  });

  it("routes transport controls to the preferred provider", async () => {
    const spotify = provider(spotifyTrack);
    const apple = provider(appleMusicTrack);
    const service = createNowPlayingService([spotify, apple]);

    await service.getNowPlaying(); // establishes the Spotify preference

    await service.control("next");
    expect(spotify.control).toHaveBeenCalledWith("next");
    expect(apple.control).not.toHaveBeenCalled();
  });

  it("routes seek to the preferred provider", async () => {
    const spotify = provider(spotifyTrack);
    const apple = provider(appleMusicTrack);
    const service = createNowPlayingService([spotify, apple]);

    await service.getNowPlaying();

    await service.seek(30_000);
    expect(spotify.seek).toHaveBeenCalledWith(30_000);
    expect(apple.seek).not.toHaveBeenCalled();
  });
});
