import { featuredContext } from "@linerfy/domain/fixtures";
import { MusicContextCard } from "@linerfy/ui";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

describe("MusicContextCard", () => {
  it("renders every consensus claim, not just the first", () => {
    const context = {
      ...featuredContext,
      consensusBlocks: [
        {
          ...featuredContext.consensusBlocks[0]!,
          claims: [
            { id: "claim-1", text: "结论一", sourceIds: ["pitchfork-nfr"] },
            { id: "claim-2", text: "结论二", sourceIds: ["guardian-nfr"] },
            {
              id: "claim-3",
              text: "结论三",
              sourceIds: ["pitchfork-nfr", "guardian-nfr"],
            },
          ],
        },
      ],
    };

    const html = renderToStaticMarkup(
      createElement(MusicContextCard, { context }),
    );

    expect(html).toContain("结论一");
    expect(html).toContain("结论二");
    expect(html).toContain("结论三");
  });

  it("attributes each claim to its own sources", () => {
    const context = {
      ...featuredContext,
      consensusBlocks: [
        {
          ...featuredContext.consensusBlocks[0]!,
          claims: [
            { id: "claim-1", text: "结论一", sourceIds: ["pitchfork-nfr"] },
            { id: "claim-2", text: "结论二", sourceIds: ["guardian-nfr"] },
          ],
        },
      ],
    };

    const html = renderToStaticMarkup(
      createElement(MusicContextCard, { context }),
    );

    expect(html).toContain("基于 Pitchfork");
    expect(html).toContain("基于 The Guardian");
  });
});
