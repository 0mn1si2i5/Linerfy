export type NowPlayingProviderName = "spotify" | "apple-music";
export type PlaybackState = "playing" | "paused";

export interface NowPlayingTrack {
  provider: NowPlayingProviderName;
  title: string;
  artist: string;
  album: string;
  state: PlaybackState;
  providerUrl?: string;
  artworkUrl?: string;
  durationMs?: number;
  positionMs?: number;
}

export interface NowPlayingProvider {
  getNowPlaying(): Promise<NowPlayingTrack | null>;
}

export type ScriptRunner = (script: string) => Promise<string>;

export const SPOTIFY_NOW_PLAYING_SCRIPT = String.raw`
const spotify = Application("Spotify");
if (!spotify.running() || spotify.playerState() === "stopped") {
  "null";
} else {
  const track = spotify.currentTrack;
  JSON.stringify({
    provider: "spotify",
    title: track.name(),
    artist: track.artist(),
    album: track.album(),
    state: spotify.playerState() === "playing" ? "playing" : "paused",
    providerUrl: track.spotifyUrl(),
    artworkUrl: track.artworkUrl(),
    durationMs: Math.round(track.duration()),
    positionMs: Math.round(spotify.playerPosition() * 1000),
  });
}
`.trim();

export const APPLE_MUSIC_NOW_PLAYING_SCRIPT = String.raw`
const music = Application("Music");
if (!music.running() || music.playerState() === "stopped") {
  "null";
} else {
  const track = music.currentTrack;
  JSON.stringify({
    provider: "apple-music",
    title: track.name(),
    artist: track.artist(),
    album: track.album(),
    state: music.playerState() === "playing" ? "playing" : "paused",
    durationMs: Math.round(track.duration() * 1000),
    positionMs: Math.round(music.playerPosition() * 1000),
  });
}
`.trim();

function isPlaybackState(value: unknown): value is PlaybackState {
  return value === "playing" || value === "paused";
}

function isAllowedArtworkUrl(
  value: unknown,
  provider: NowPlayingProviderName,
): value is string {
  if (value === undefined) return true;
  if (typeof value !== "string" || provider !== "spotify") return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "i.scdn.co";
  } catch {
    return false;
  }
}

function parseTrack(
  output: string,
  provider: NowPlayingProviderName,
): NowPlayingTrack | null {
  const value: unknown = JSON.parse(output.trim() || "null");
  if (value === null) return null;
  if (typeof value !== "object")
    throw new Error(`Invalid ${provider} now-playing result`);

  const track = value as Record<string, unknown>;
  const validTiming =
    (track.durationMs === undefined && track.positionMs === undefined) ||
    (typeof track.durationMs === "number" &&
      Number.isFinite(track.durationMs) &&
      track.durationMs > 0 &&
      typeof track.positionMs === "number" &&
      Number.isFinite(track.positionMs) &&
      track.positionMs >= 0);
  if (
    track.provider !== provider ||
    typeof track.title !== "string" ||
    typeof track.artist !== "string" ||
    typeof track.album !== "string" ||
    !isPlaybackState(track.state) ||
    (track.providerUrl !== undefined &&
      typeof track.providerUrl !== "string") ||
    !isAllowedArtworkUrl(track.artworkUrl, provider) ||
    !validTiming
  ) {
    throw new Error(`Invalid ${provider} now-playing result`);
  }

  return {
    provider,
    title: track.title,
    artist: track.artist,
    album: track.album,
    state: track.state,
    ...(typeof track.providerUrl === "string"
      ? { providerUrl: track.providerUrl }
      : {}),
    ...(typeof track.artworkUrl === "string"
      ? { artworkUrl: track.artworkUrl }
      : {}),
    ...(typeof track.durationMs === "number" &&
    typeof track.positionMs === "number"
      ? {
          durationMs: track.durationMs,
          positionMs: Math.min(track.positionMs, track.durationMs),
        }
      : {}),
  };
}

function createProvider(
  provider: NowPlayingProviderName,
  script: string,
  runScript: ScriptRunner,
): NowPlayingProvider {
  return {
    async getNowPlaying() {
      return parseTrack(await runScript(script), provider);
    },
  };
}

export function createSpotifyProvider(
  runScript: ScriptRunner,
): NowPlayingProvider {
  return createProvider("spotify", SPOTIFY_NOW_PLAYING_SCRIPT, runScript);
}

export function createAppleMusicProvider(
  runScript: ScriptRunner,
): NowPlayingProvider {
  return createProvider(
    "apple-music",
    APPLE_MUSIC_NOW_PLAYING_SCRIPT,
    runScript,
  );
}

/**
 * Combine providers, preferring the one that is actually playing. When several
 * are playing (or none are), the provider that last succeeded wins, so a stable
 * preference emerges across polls without ever overriding a playing player.
 */
export function createNowPlayingService(
  providers: NowPlayingProvider[],
): NowPlayingProvider {
  let lastPreferred: NowPlayingProviderName | null = null;

  return {
    async getNowPlaying() {
      const settled = await Promise.allSettled(
        providers.map((provider) => provider.getNowPlaying()),
      );
      const tracks: NowPlayingTrack[] = [];
      for (const result of settled) {
        if (result.status === "fulfilled" && result.value !== null) {
          tracks.push(result.value);
        }
      }
      if (tracks.length === 0) return null;

      const playing = tracks.filter((track) => track.state === "playing");
      const candidates = playing.length > 0 ? playing : tracks;
      const chosen =
        candidates.find((track) => track.provider === lastPreferred) ??
        candidates[0]!;
      lastPreferred = chosen.provider;
      return chosen;
    },
  };
}
