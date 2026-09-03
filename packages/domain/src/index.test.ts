import { describe, expect, it } from "vitest";

import { musicContextSchema } from "./index";
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
