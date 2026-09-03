import { describe, expect, it } from "vitest";

import { contextApiResponseSchema, musicContextSchema } from "./index";
import { featuredContext } from "./fixtures";

describe("musicContextSchema", () => {
  it("accepts a release context with cited claims", () => {
    const parsed = musicContextSchema.parse(featuredContext);

    expect(parsed.release.title).toBe("Norman Fucking Rockwell!");
    expect(parsed.sourceSummaries[0]?.claims[0]?.sourceIds).toContain(
      "pitchfork-nfr",
    );
  });

  it("rejects claims that reference an absent source", () => {
    const context = structuredClone(featuredContext);
    context.sourceSummaries[0]!.claims[0]!.sourceIds = ["missing-source"];

    expect(() => musicContextSchema.parse(context)).toThrow(
      "Every cited claim must reference a source in this context",
    );
  });
});

describe("contextApiResponseSchema", () => {
  it("accepts a ready response that carries a valid context", () => {
    const parsed = contextApiResponseSchema.parse({
      status: "ready",
      context: featuredContext,
    });
    expect(parsed.status).toBe("ready");
  });

  it("rejects a ready response that omits its context", () => {
    expect(() => contextApiResponseSchema.parse({ status: "ready" })).toThrow();
  });

  it("accepts the terminal states without a context", () => {
    for (const status of ["unavailable", "ambiguous", "failed"]) {
      expect(contextApiResponseSchema.parse({ status }).status).toBe(status);
    }
  });

  it("rejects an unknown status", () => {
    expect(() =>
      contextApiResponseSchema.parse({ status: "paused" }),
    ).toThrow();
  });
});
