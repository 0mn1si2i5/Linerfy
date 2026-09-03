import { musicContextSchema, type MusicContext } from "./index";

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
  summary_kind: string;
  license_pool: string;
  license_url: string;
  source_id: string | null;
  attribution: string;
  ai_modified: boolean;
  skipped_reason: string | null;
  // Immutable-generation columns (added by the R4 migration). The reader only
  // depends on `status`, so these are optional on the read-side row shape.
  scope?: string;
  published_at?: string | null;
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
 * the database's uuid-keyed rows back into the slug-keyed display contract. It
 * anchors on `releases[0]` and scopes every other array to that release (or its
 * own ids), so a second album's rows can never bleed into the result. The
 * result is validated with `musicContextSchema.parse` before it is returned.
 */
export function assembleMusicContext(catalog: CatalogRows): MusicContext {
  const release = catalog.releases[0];
  if (!release) {
    throw new Error("catalog is missing a release");
  }
  const artist = catalog.artists.find((a) => a.id === release.artist_id);
  if (!artist) {
    throw new Error("catalog is missing the release's artist");
  }

  const sourceByUuid = new Map(catalog.review_sources.map((s) => [s.id, s]));
  const documents = catalog.review_documents.filter(
    (d) => d.release_id === release.id,
  );
  const docByUuid = new Map(documents.map((d) => [d.id, d]));

  const sources = documents
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

  const excerpts = catalog.review_excerpts
    .filter((e) => docByUuid.has(e.document_id))
    .map((e) => {
      const doc = docByUuid.get(e.document_id)!;
      return {
        id: `${doc.slug}-excerpt`,
        sourceId: doc.slug,
        text: e.excerpt,
        kind: e.is_paraphrase
          ? ("paraphrase" as const)
          : ("quotation" as const),
      };
    });

  const genres = catalog.genres
    .filter((g) => g.release_id === release.id)
    .map((g) => ({
      name: g.name,
      sourceIds: catalog.genre_sources
        .filter((gs) => gs.genre_id === g.id)
        .map((gs) => docByUuid.get(gs.document_id)?.slug)
        .filter((slug): slug is string => Boolean(slug)),
    }));

  // Only the current published generation per scope is public. Immutable
  // generations mean candidate/superseded/failed rows coexist with the one
  // published row; a half-built or superseded generation must never leak.
  // Never `.find()` a single run — that would silently drop other license pools.
  const releaseSummaries = catalog.summary_runs.filter(
    (r) => r.release_id === release.id && r.status === "published",
  );
  const publicationBySlug = new Map(
    catalog.review_sources.map((s) => [s.slug, s.publication]),
  );

  const claimsFor = (run: SummaryRunRow) =>
    catalog.claims
      .filter((c) => c.summary_run_id === run.id)
      .sort((a, b) => a.claim_order - b.claim_order)
      .map((c) => ({
        id: `claim-${c.claim_order + 1}`,
        text: c.claim_text,
        sourceIds: catalog.claim_sources
          .filter((cs) => cs.claim_id === c.id)
          .map((cs) => docByUuid.get(cs.document_id)?.slug)
          .filter((slug): slug is string => Boolean(slug)),
      }));

  const sourceSummaries: Array<{
    source: { id: string; publication: string };
    license: { id: string; url: string };
    attribution: string;
    aiModified: boolean;
    claims: ReturnType<typeof claimsFor>;
  }> = [];
  const sourceIdsByPool = new Map<string, string[]>();
  for (const run of releaseSummaries) {
    if (run.summary_kind !== "source") continue;
    const sourceId = run.source_id ?? "";
    sourceSummaries.push({
      source: {
        id: sourceId,
        publication: publicationBySlug.get(sourceId) ?? "",
      },
      license: { id: run.license_pool, url: run.license_url },
      attribution: run.attribution,
      aiModified: run.ai_modified,
      claims: claimsFor(run),
    });
    const ids = sourceIdsByPool.get(run.license_pool) ?? [];
    if (sourceId && !ids.includes(sourceId)) {
      ids.push(sourceId);
    }
    sourceIdsByPool.set(run.license_pool, ids);
  }

  const consensusBlocks = releaseSummaries
    .filter((run) => run.summary_kind === "consensus")
    .map((run) => {
      const block: {
        licensePool: string;
        license: { id: string; url: string };
        sourceIds: string[];
        attribution: string;
        aiModified: boolean;
        claims: ReturnType<typeof claimsFor>;
        skippedReason?: string;
      } = {
        licensePool: run.license_pool,
        license: { id: run.license_pool, url: run.license_url },
        sourceIds: sourceIdsByPool.get(run.license_pool) ?? [],
        attribution: run.attribution,
        aiModified: run.ai_modified,
        claims: claimsFor(run),
      };
      if (run.skipped_reason) {
        block.skippedReason = run.skipped_reason;
      }
      return block;
    });

  return musicContextSchema.parse({
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
    recordings: catalog.recordings
      .filter((r) => r.release_id === release.id)
      .map((r) => ({
        id: r.id,
        title: r.title,
        releaseId: release.slug,
        providerIds: {},
      })),
    genres,
    sources,
    excerpts,
    sourceSummaries,
    consensusBlocks,
  });
}
