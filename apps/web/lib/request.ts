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
});

export type NowPlayingRequest = z.infer<typeof nowPlayingRequestSchema>;

function normalize(value: string): string {
  return value.toLowerCase().replace(/\s+/g, " ").trim();
}

/** Mirrors `NowPlayingRequest.fingerprint()` in the ingest package. */
export function requestFingerprint(request: NowPlayingRequest): string {
  const key = `${request.provider}:${normalize(request.artist)}|${normalize(request.album)}`;
  return createHash("sha256").update(key, "utf8").digest("hex");
}

function slugify(text: string): string {
  const slug = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "unknown";
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
