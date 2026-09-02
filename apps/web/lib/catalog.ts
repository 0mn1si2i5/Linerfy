import type { MusicContext } from "@linerfy/domain";
import {
  assembleMusicContext,
  type CatalogRows,
} from "@linerfy/domain/from-catalog";
import { createClient } from "@supabase/supabase-js";

import { requireEnv } from "./env";

const FEATURED_SLUG = "norman-fucking-rockwell";

/**
 * The outcome of reading the featured album's context from Supabase.
 *
 * `not-found` is a legitimate empty state ("this album isn't covered yet");
 * `query-failed` and `invalid` are failures that must never be shown as that.
 */
export type FeaturedContextResult =
  | { status: "ok"; context: MusicContext }
  | { status: "not-found" }
  | { status: "query-failed"; message: string }
  | { status: "invalid"; message: string };

function createSupabase() {
  return createClient(
    requireEnv("SUPABASE_URL"),
    requireEnv("SUPABASE_PUBLISHABLE_KEY"),
  );
}

/**
 * Read the featured album's normalized catalog rows from Supabase and reassemble
 * the public MusicContext. Runs only on the server; the anon key never reaches
 * the browser bundle.
 *
 * Every join-table query is scoped to this release's own ids, so a second
 * album's excerpts, genres, claims, or citations cannot leak into the result.
 */
export async function getFeaturedContext(): Promise<FeaturedContextResult> {
  const supabase = createSupabase();

  const { data: release, error: releaseError } = await supabase
    .from("releases")
    .select("*")
    .eq("slug", FEATURED_SLUG)
    .maybeSingle();

  if (releaseError) {
    return { status: "query-failed", message: releaseError.message };
  }
  if (!release) {
    return { status: "not-found" };
  }

  const releaseId = release.id;

  // Entities addressed directly by this release's id.
  const [
    artistResult,
    genresResult,
    sourcesResult,
    documentsResult,
    summaryRunsResult,
    recordingsResult,
  ] = await Promise.all([
    supabase
      .from("artists")
      .select("*")
      .eq("id", release.artist_id)
      .maybeSingle(),
    supabase.from("genres").select("*").eq("release_id", releaseId),
    supabase.from("review_sources").select("*"),
    supabase.from("review_documents").select("*").eq("release_id", releaseId),
    supabase.from("summary_runs").select("*").eq("release_id", releaseId),
    supabase.from("recordings").select("*").eq("release_id", releaseId),
  ]);

  const firstPhase = [
    artistResult,
    genresResult,
    sourcesResult,
    documentsResult,
    summaryRunsResult,
    recordingsResult,
  ];
  const failed = firstPhase.find((result) => result.error);
  if (failed?.error) {
    return { status: "query-failed", message: failed.error.message };
  }

  const genreIds = (genresResult.data ?? []).map((g) => g.id);
  const documentIds = (documentsResult.data ?? []).map((d) => d.id);
  const summaryRunIds = (summaryRunsResult.data ?? []).map((r) => r.id);

  // Join tables scoped to this release's own entities.
  const [genreSourcesResult, excerptsResult, claimsResult] = await Promise.all([
    supabase.from("genre_sources").select("*").in("genre_id", genreIds),
    supabase.from("review_excerpts").select("*").in("document_id", documentIds),
    supabase.from("claims").select("*").in("summary_run_id", summaryRunIds),
  ]);

  const secondPhase = [genreSourcesResult, excerptsResult, claimsResult];
  const failedJoin = secondPhase.find((result) => result.error);
  if (failedJoin?.error) {
    return { status: "query-failed", message: failedJoin.error.message };
  }

  const claimIds = (claimsResult.data ?? []).map((c) => c.id);
  const { data: claimSources, error: claimSourcesError } = await supabase
    .from("claim_sources")
    .select("*")
    .in("claim_id", claimIds);
  if (claimSourcesError) {
    return { status: "query-failed", message: claimSourcesError.message };
  }

  const catalog: CatalogRows = {
    artists: artistResult.data ? [artistResult.data] : [],
    releases: [release],
    genres: genresResult.data ?? [],
    genre_sources: genreSourcesResult.data ?? [],
    review_sources: sourcesResult.data ?? [],
    review_documents: documentsResult.data ?? [],
    review_excerpts: excerptsResult.data ?? [],
    summary_runs: summaryRunsResult.data ?? [],
    claims: claimsResult.data ?? [],
    claim_sources: claimSources ?? [],
    recordings: recordingsResult.data ?? [],
  };

  try {
    return { status: "ok", context: assembleMusicContext(catalog) };
  } catch (error) {
    console.error("invalid featured context:", error);
    return {
      status: "invalid",
      message: error instanceof Error ? error.message : String(error),
    };
  }
}
