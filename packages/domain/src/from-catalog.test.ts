import { describe, expect, it } from "vitest";

import { assembleMusicContext, type CatalogRows } from "./from-catalog";
import { musicContextSchema } from "./index";

const catalog: CatalogRows = {
  artists: [{ id: "a1", slug: "lana-del-rey", name: "Lana Del Rey" }],
  releases: [
    {
      id: "r1",
      slug: "norman-fucking-rockwell",
      artist_id: "a1",
      title: "Norman Fucking Rockwell!",
      release_date: "2019-01-01",
      artwork_url: "https://example.com/art.jpg",
    },
  ],
  genres: [
    { id: "g1", release_id: "r1", name: "Singer-Songwriter" },
    { id: "g2", release_id: "r1", name: "Psychedelic Pop" },
  ],
  genre_sources: [
    { genre_id: "g1", document_id: "d1" },
    { genre_id: "g2", document_id: "d2" },
  ],
  review_sources: [
    {
      id: "s1",
      slug: "pitchfork",
      publication: "Pitchfork",
      homepage_url: "https://pitchfork.com",
    },
    {
      id: "s2",
      slug: "guardian",
      publication: "The Guardian",
      homepage_url: "https://www.theguardian.com",
    },
  ],
  review_documents: [
    {
      id: "d1",
      slug: "pitchfork-nfr",
      release_id: "r1",
      source_id: "s1",
      source_url:
        "https://pitchfork.com/reviews/albums/lana-del-rey-norman-fucking-rockwell/",
      title: "Norman Fucking Rockwell!",
      author: "Jenn Pelly",
      published_at: "2019-09-03",
      score: 9.4,
      score_scale: 10,
      status: "published",
    },
    {
      id: "d2",
      slug: "guardian-nfr",
      release_id: "r1",
      source_id: "s2",
      source_url:
        "https://www.theguardian.com/music/2019/aug/30/lana-del-rey-norman-fucking-rockwell-review",
      title: "Norman Fucking Rockwell! review",
      author: "Alexis Petridis",
      published_at: "2019-08-30",
      score: 4,
      score_scale: 5,
      status: "published",
    },
  ],
  review_excerpts: [
    {
      id: "e1",
      document_id: "d1",
      excerpt:
        "The review treats the album as a major statement built from patient songwriting and a sharply observed American mythology.",
      is_paraphrase: true,
    },
    {
      id: "e2",
      document_id: "d2",
      excerpt:
        "The review emphasizes how classic songwriting craft and an unstable cultural backdrop strengthen one another.",
      is_paraphrase: true,
    },
  ],
  summary_runs: [
    {
      id: "sr1",
      release_id: "r1",
      model: "fixture-editorial-v1",
      locale: "zh-CN",
      corpus_hash: "fixture:nfr:v1",
      generated_at: "2026-09-02T00:00:00Z",
      status: "published",
    },
  ],
  claims: [
    {
      id: "c1",
      summary_run_id: "sr1",
      claim_order: 0,
      claim_text:
        "评论者普遍认为，这张专辑把精细的写作、松弛的制作与美国流行文化的衰败感结合成了 Lana Del Rey 最完整的表达之一。",
    },
  ],
  claim_sources: [
    { claim_id: "c1", document_id: "d1" },
    { claim_id: "c1", document_id: "d2" },
  ],
  recordings: [],
};

describe("assembleMusicContext", () => {
  it("reassembles a valid public context from catalog rows", () => {
    const parsed = musicContextSchema.parse(assembleMusicContext(catalog));

    expect(parsed.release.id).toBe("norman-fucking-rockwell");
    expect(parsed.artist.id).toBe("lana-del-rey");
    expect(parsed.release.year).toBe(2019);
    expect(parsed.sources).toHaveLength(2);
    expect(parsed.sources[0]?.publication).toBe("Pitchfork");
    expect(parsed.genres.map((g) => g.name)).toEqual([
      "Singer-Songwriter",
      "Psychedelic Pop",
    ]);
    expect(parsed.summary.corpusHash).toBe("fixture:nfr:v1");
    expect(parsed.summary.claims[0]?.sourceIds).toContain("pitchfork-nfr");
  });

  it("excludes non-published documents", () => {
    const withDraft: CatalogRows = {
      ...catalog,
      review_documents: [
        ...catalog.review_documents,
        {
          id: "d3",
          slug: "draft-doc",
          release_id: "r1",
          source_id: "s1",
          source_url: "https://example.com/draft",
          title: "Draft",
          author: null,
          published_at: null,
          score: null,
          score_scale: null,
          status: "draft",
        },
      ],
    };

    expect(assembleMusicContext(withDraft).sources).toHaveLength(2);
  });
});
