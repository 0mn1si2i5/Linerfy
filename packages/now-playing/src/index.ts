export type NowPlayingProviderName = "spotify" | "apple-music";

export interface NowPlayingTrack {
  provider: NowPlayingProviderName;
  title: string;
  artist: string;
  album: string;
  providerUrl?: string;
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
    providerUrl: track.spotifyUrl(),
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
  });
}
`.trim();

function parseTrack(
  output: string,
  provider: NowPlayingProviderName,
): NowPlayingTrack | null {
  const value: unknown = JSON.parse(output.trim() || "null");
  if (value === null) return null;
  if (typeof value !== "object")
    throw new Error(`Invalid ${provider} now-playing result`);

  const track = value as Record<string, unknown>;
  if (
    track.provider !== provider ||
    typeof track.title !== "string" ||
    typeof track.artist !== "string" ||
    typeof track.album !== "string" ||
    (track.providerUrl !== undefined && typeof track.providerUrl !== "string")
  ) {
    throw new Error(`Invalid ${provider} now-playing result`);
  }

  return {
    provider,
    title: track.title,
    artist: track.artist,
    album: track.album,
    ...(typeof track.providerUrl === "string"
      ? { providerUrl: track.providerUrl }
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

export function createNowPlayingService(
  providers: NowPlayingProvider[],
): NowPlayingProvider {
  return {
    async getNowPlaying() {
      for (const provider of providers) {
        try {
          const track = await provider.getNowPlaying();
          if (track) return track;
        } catch {
          // A player may be closed or automation permission may be denied.
        }
      }
      return null;
    },
  };
}
