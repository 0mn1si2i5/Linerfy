export type NowPlayingProviderName = "spotify" | "apple-music";
export type PlaybackState = "playing" | "paused";

/** Fixed transport actions the renderer may request. Never an arbitrary command. */
export type PlaybackAction = "previous" | "toggle" | "next";

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
  /** Set on concrete providers so the service can route transport controls. */
  providerName?: NowPlayingProviderName;
  getNowPlaying(): Promise<NowPlayingTrack | null>;
  control(action: PlaybackAction): Promise<void>;
  seek(positionMs: number): Promise<void>;
}

/** Run a bundled JXA program, optionally with trailing argv (for seek). */
export type ScriptRunner = (script: string, args?: string[]) => Promise<string>;

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

export const SPOTIFY_CONTROL_SCRIPTS: Record<PlaybackAction, string> = {
  previous: `Application("Spotify").previousTrack();`,
  toggle: `Application("Spotify").playpause();`,
  next: `Application("Spotify").nextTrack();`,
};

export const APPLE_MUSIC_CONTROL_SCRIPTS: Record<PlaybackAction, string> = {
  previous: `Application("Music").backTrack();`,
  toggle: `Application("Music").playpause();`,
  next: `Application("Music").nextTrack();`,
};

// Seek uses run(argv) so the target position is a separate argument, never
// interpolated into the program text. argv[0] is a validated number (seconds).
export const SPOTIFY_SEEK_SCRIPT = `function run(argv) { Application("Spotify").setPlayerPosition(parseFloat(argv[0])); }`;
export const APPLE_MUSIC_SEEK_SCRIPT = `function run(argv) { Application("Music").setPlayerPosition(parseFloat(argv[0])); }`;

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
  nowPlayingScript: string,
  controlScripts: Record<PlaybackAction, string>,
  seekScript: string,
  runScript: ScriptRunner,
): NowPlayingProvider {
  return {
    providerName: provider,
    async getNowPlaying() {
      return parseTrack(await runScript(nowPlayingScript), provider);
    },
    async control(action) {
      await runScript(controlScripts[action]);
    },
    async seek(positionMs) {
      // The caller validates the position; here it is only converted to the
      // seconds the player APIs expect, passed as argv[0], never interpolated.
      await runScript(seekScript, [String(positionMs / 1000)]);
    },
  };
}

export function createSpotifyProvider(
  runScript: ScriptRunner,
): NowPlayingProvider {
  return createProvider(
    "spotify",
    SPOTIFY_NOW_PLAYING_SCRIPT,
    SPOTIFY_CONTROL_SCRIPTS,
    SPOTIFY_SEEK_SCRIPT,
    runScript,
  );
}

export function createAppleMusicProvider(
  runScript: ScriptRunner,
): NowPlayingProvider {
  return createProvider(
    "apple-music",
    APPLE_MUSIC_NOW_PLAYING_SCRIPT,
    APPLE_MUSIC_CONTROL_SCRIPTS,
    APPLE_MUSIC_SEEK_SCRIPT,
    runScript,
  );
}

/**
 * Combine providers, preferring the one that is actually playing. When several
 * are playing (or none are), the provider that last succeeded wins, so a stable
 * preference emerges across polls without ever overriding a playing player.
 * Transport controls route to the same preferred provider.
 */
export function createNowPlayingService(
  providers: NowPlayingProvider[],
): NowPlayingProvider {
  let lastPreferred: NowPlayingProviderName | null = null;

  function preferred(): NowPlayingProvider | null {
    const provider = providers.find((p) => p.providerName === lastPreferred);
    return provider ?? providers[0] ?? null;
  }

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
    async control(action) {
      await preferred()?.control(action);
    },
    async seek(positionMs) {
      await preferred()?.seek(positionMs);
    },
  };
}
