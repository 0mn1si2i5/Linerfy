import type { MusicContext } from "./index";

// Row shapes matching the Supabase catalog migration. These are the column
// names the Python `to_rows` writer and this reader both agree on.

export interface ArtistRow {
  id: string;
  slug: string;
  name: string;
}

export interface ReleaseRow {
  id: string;
  slug: string;
  artist_id: string;
  title: string;
  release_date: string | null;
  artwork_url: string | null;
}

export interface GenreRow {
  id: string;
  release_id: string;
  name: string;
}

export interface GenreSourceRow {
  genre_id: string;
  document_id: string;
}

export interface ReviewSourceRow {
  id: string;
  slug: string;
  publication: string;
  homepage_url: string;
}

export interface ReviewDocumentRow {
  id: string;
  slug: string;
  release_id: string;
  source_id: string;
  source_url: string;
  title: string;
  author: string | null;
  published_at: string | null;
  score: number | null;
  score_scale: number | null;
  status: string;
}

export interface ReviewExcerptRow {
  id: string;
  document_id: string;
  excerpt: string;
  is_paraphrase: boolean;
}

export interface SummaryRunRow {
  id: string;
  release_id: string;
  model: string;
  locale: string;
  corpus_hash: string;
  generated_at: string;
  status: string;
}

export interface ClaimRow {
  id: string;
  summary_run_id: string;
  claim_order: number;
  claim_text: string;
}

export interface ClaimSourceRow {
  claim_id: string;
  document_id: string;
}

export interface RecordingRow {
  id: string;
  release_id: string;
  title: string;
}

export interface CatalogRows {
  artists: ArtistRow[];
  releases: ReleaseRow[];
  genres: GenreRow[];
  genre_sources: GenreSourceRow[];
  review_sources: ReviewSourceRow[];
  review_documents: ReviewDocumentRow[];
  review_excerpts: ReviewExcerptRow[];
  summary_runs: SummaryRunRow[];
  claims: ClaimRow[];
  claim_sources: ClaimSourceRow[];
  recordings: RecordingRow[];
}

/**
 * Reassemble the public MusicContext from normalized catalog rows.
 *
 * This is the read-side counterpart to the Python `to_public` mapping: it turns
 * the database's uuid-keyed rows back into the slug-keyed display contract.
 */
export function assembleMusicContext(catalog: CatalogRows): MusicContext {
  const artist = catalog.artists[0];
  const release = catalog.releases[0];
  if (!artist || !release) {
    throw new Error("catalog is missing an artist or release");
  }

  const sourceByUuid = new Map(catalog.review_sources.map((s) => [s.id, s]));
  const docByUuid = new Map(catalog.review_documents.map((d) => [d.id, d]));

  const sources = catalog.review_documents
    .filter((d) => d.status === "published")
    .map((d) => {
      const source = {
        id: d.slug,
        publication: sourceByUuid.get(d.source_id)?.publication ?? "",
        title: d.title,
        url: d.source_url,
        ...(d.author ? { author: d.author } : {}),
        ...(d.published_at ? { publishedAt: d.published_at } : {}),
        ...(d.score !== null && d.score_scale !== null
          ? { score: { value: d.score, scale: d.score_scale } }
          : {}),
      };
      return source;
    });

  const excerpts = catalog.review_excerpts.map((e) => ({
    id: `${docByUuid.get(e.document_id)?.slug ?? e.id}-excerpt`,
    sourceId: docByUuid.get(e.document_id)?.slug ?? "",
    text: e.excerpt,
    kind: e.is_paraphrase ? ("paraphrase" as const) : ("quotation" as const),
  }));

  const genres = catalog.genres.map((g) => ({
    name: g.name,
    sourceIds: catalog.genre_sources
      .filter((gs) => gs.genre_id === g.id)
      .map((gs) => docByUuid.get(gs.document_id)?.slug)
      .filter((slug): slug is string => Boolean(slug)),
  }));

  const summaryRun = catalog.summary_runs[0];
  const claims = summaryRun
    ? catalog.claims
        .filter((c) => c.summary_run_id === summaryRun.id)
        .sort((a, b) => a.claim_order - b.claim_order)
        .map((c) => ({
          id: `claim-${c.claim_order + 1}`,
          text: c.claim_text,
          sourceIds: catalog.claim_sources
            .filter((cs) => cs.claim_id === c.id)
            .map((cs) => docByUuid.get(cs.document_id)?.slug)
            .filter((slug): slug is string => Boolean(slug)),
        }))
    : [];

  return {
    artist: { id: artist.slug, name: artist.name },
    release: {
      id: release.slug,
      title: release.title,
      artistId: artist.slug,
      year: release.release_date
        ? Number(release.release_date.slice(0, 4))
        : new Date().getUTCFullYear(),
      ...(release.artwork_url ? { artworkUrl: release.artwork_url } : {}),
    },
    recordings: catalog.recordings.map((r) => ({
      id: r.id,
      title: r.title,
      releaseId: release.slug,
      providerIds: {},
    })),
    genres,
    sources,
    excerpts,
    summary: {
      locale: summaryRun?.locale ?? "en",
      corpusHash: summaryRun?.corpus_hash ?? "",
      model: summaryRun?.model ?? "",
      generatedAt: summaryRun?.generated_at ?? new Date(0).toISOString(),
      claims,
    },
  };
}
