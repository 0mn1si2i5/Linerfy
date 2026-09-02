import {
  assembleMusicContext,
  type CatalogRows,
} from "@linerfy/domain/from-catalog";
import { createClient } from "@supabase/supabase-js";

const FEATURED_SLUG = "norman-fucking-rockwell";

function createSupabase() {
  return createClient(
    process.env.SUPABASE_URL!,
    process.env.SUPABASE_ANON_KEY!,
  );
}

/**
 * Read the featured album's normalized catalog rows from Supabase and reassemble
 * the public MusicContext. Runs only on the server; the anon key never reaches
 * the browser bundle.
 */
export async function getFeaturedContext() {
  const supabase = createSupabase();

  const { data: release } = await supabase
    .from("releases")
    .select("*")
    .eq("slug", FEATURED_SLUG)
    .single();

  if (!release) return null;

  const releaseId = release.id;

  const [
    artist,
    genres,
    genreSources,
    sources,
    documents,
    excerpts,
    summaryRuns,
    claims,
    claimSources,
    recordings,
  ] = await Promise.all([
    supabase.from("artists").select("*").eq("id", release.artist_id).single(),
    supabase.from("genres").select("*").eq("release_id", releaseId),
    supabase.from("genre_sources").select("*"),
    supabase.from("review_sources").select("*"),
    supabase.from("review_documents").select("*").eq("release_id", releaseId),
    supabase.from("review_excerpts").select("*"),
    supabase.from("summary_runs").select("*").eq("release_id", releaseId),
    supabase.from("claims").select("*"),
    supabase.from("claim_sources").select("*"),
    supabase.from("recordings").select("*").eq("release_id", releaseId),
  ]);

  const catalog: CatalogRows = {
    artists: artist.data ? [artist.data] : [],
    releases: [release],
    genres: genres.data ?? [],
    genre_sources: genreSources.data ?? [],
    review_sources: sources.data ?? [],
    review_documents: documents.data ?? [],
    review_excerpts: excerpts.data ?? [],
    summary_runs: summaryRuns.data ?? [],
    claims: claims.data ?? [],
    claim_sources: claimSources.data ?? [],
    recordings: recordings.data ?? [],
  };

  return assembleMusicContext(catalog);
}
