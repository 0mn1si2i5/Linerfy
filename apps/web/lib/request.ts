import { createHash } from "node:crypto";

import { z } from "zod";

/**
 * The untrusted now-playing request the authenticated API accepts. Bounds match
 * the Python `NowPlayingRequest` in `ingest/src/linerfy_ingest/request.py`.
 */
export const nowPlayingRequestSchema = z.object({
  provider: z.enum(["spotify", "apple-music"]),
  title: z.string().min(1).max(500),
  artist: z.string().min(1).max(500),
  album: z.string().min(1).max(500),
  providerUrl: z.string().max(2048).optional(),
  state: z.enum(["playing", "paused"]).default("playing"),
  retry: z.boolean().optional(),
});

export type NowPlayingRequest = z.infer<typeof nowPlayingRequestSchema>;

function normalize(value: string): string {
  return value.toLowerCase().replace(/\s+/g, " ").trim();
}

function digest(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

/**
 * Mirrors `NowPlayingRequest.fingerprint()` in the ingest package. Each field is
 * hashed to a fixed-length hex first, then combined, so a field that contains
 * `:` or `|` can never collide with the separator and the two ends stay
 * byte-for-byte identical (see request.py).
 */
export function requestFingerprint(request: NowPlayingRequest): string {
  const artist = digest(normalize(request.artist));
  const album = digest(normalize(request.album));
  return digest(`${request.provider}:${artist}:${album}`);
}

/** Read compatibility for jobs queued before per-field hashing. */
export function legacyRequestFingerprint(request: NowPlayingRequest): string {
  return digest(
    `${request.provider}:${normalize(request.artist)}|${normalize(request.album)}`,
  );
}

/**
 * Mirrors `_slugify()` in the ingest pipeline. A readable ASCII slug is only
 * safe when the name is entirely ASCII: otherwise stripping non-ASCII letters
 * (accented Latin, CJK, …) collapses distinct names onto the same slug (the
 * "unknown-unknown" collision). Non-ASCII names hash their NFC-normalized form
 * instead, so identity is lossless and identical on both sides.
 */
function slugify(text: string): string {
  const isAscii = /^[\x00-\x7F]*$/.test(text);
  if (isAscii) {
    const slug = text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return slug || "unknown";
  }
  return digest(text.normalize("NFC")).slice(0, 12);
}

/** Mirrors `_release_slug()` in the ingest pipeline. */
export function releaseSlug(artist: string, album: string): string {
  return `${slugify(artist)}-${slugify(album)}`;
}

/**
 * The payload persisted into `enrichment_jobs.payload`. The Python
 * `NowPlayingRequest` uses snake_case (`provider_url`) and rejects unknown
 * fields, so this is the single place the JS camelCase contract is mapped to
 * the ingest contract before anything is written to the database.
 */
export interface IngestPayload {
  provider: "spotify" | "apple-music";
  title: string;
  artist: string;
  album: string;
  state: "playing" | "paused";
  provider_url?: string;
}

export function toIngestPayload(request: NowPlayingRequest): IngestPayload {
  return {
    provider: request.provider,
    title: request.title,
    artist: request.artist,
    album: request.album,
    state: request.state,
    ...(request.providerUrl ? { provider_url: request.providerUrl } : {}),
  };
}
