import { z } from "zod";

export const artistSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
});

export const releaseSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  artistId: z.string().min(1),
  year: z.number().int().min(1900).max(2100),
  artworkUrl: z.url().optional(),
});

export const recordingSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  releaseId: z.string().min(1),
  providerIds: z.record(z.string(), z.string().min(1)).default({}),
});

export const reviewSourceSchema = z.object({
  id: z.string().min(1),
  publication: z.string().min(1),
  author: z.string().min(1).optional(),
  title: z.string().min(1),
  url: z.url(),
  publishedAt: z.iso.date().optional(),
  score: z
    .object({
      value: z.number().nonnegative(),
      scale: z.number().positive(),
    })
    .optional(),
});

export const reviewExcerptSchema = z.object({
  id: z.string().min(1),
  sourceId: z.string().min(1),
  text: z.string().min(1).max(500),
  kind: z.enum(["quotation", "paraphrase"]),
});

export const genreSchema = z.object({
  name: z.string().min(1),
  sourceIds: z.array(z.string().min(1)).min(1),
});

export const citedClaimSchema = z.object({
  id: z.string().min(1),
  text: z.string().min(1),
  sourceIds: z.array(z.string().min(1)).min(1),
});

export const citedSummarySchema = z.object({
  locale: z.string().min(2),
  corpusHash: z.string().min(1),
  model: z.string().min(1),
  generatedAt: z.iso.datetime(),
  claims: z.array(citedClaimSchema).min(1),
});

export const musicContextSchema = z
  .object({
    artist: artistSchema,
    release: releaseSchema,
    recordings: z.array(recordingSchema),
    genres: z.array(genreSchema),
    sources: z.array(reviewSourceSchema).min(1),
    excerpts: z.array(reviewExcerptSchema),
    summary: citedSummarySchema,
  })
  .superRefine((context, refinement) => {
    const sourceIds = new Set(context.sources.map((source) => source.id));
    const citedIds = [
      ...context.summary.claims.flatMap((claim) => claim.sourceIds),
      ...context.genres.flatMap((genre) => genre.sourceIds),
      ...context.excerpts.map((excerpt) => excerpt.sourceId),
    ];

    if (citedIds.some((sourceId) => !sourceIds.has(sourceId))) {
      refinement.addIssue({
        code: "custom",
        message: "Every cited claim must reference a source in this context",
      });
    }

    if (context.release.artistId !== context.artist.id) {
      refinement.addIssue({
        code: "custom",
        message: "Release artistId must match the context artist",
      });
    }

    if (
      context.recordings.some(
        (recording) => recording.releaseId !== context.release.id,
      )
    ) {
      refinement.addIssue({
        code: "custom",
        message: "Every recording must belong to the context release",
      });
    }
  });

export type Artist = z.infer<typeof artistSchema>;
export type Release = z.infer<typeof releaseSchema>;
export type Recording = z.infer<typeof recordingSchema>;
export type ReviewSource = z.infer<typeof reviewSourceSchema>;
export type ReviewExcerpt = z.infer<typeof reviewExcerptSchema>;
export type Genre = z.infer<typeof genreSchema>;
export type CitedClaim = z.infer<typeof citedClaimSchema>;
export type CitedSummary = z.infer<typeof citedSummarySchema>;
export type MusicContext = z.infer<typeof musicContextSchema>;
