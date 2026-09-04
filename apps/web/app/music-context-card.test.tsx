import { featuredContext } from "@linerfy/domain/fixtures";
import { MusicContextCard } from "@linerfy/ui";
import { createElement } from "react";
import type { ComponentType } from "react";
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

    expect(html).toContain("来源：Pitchfork");
    expect(html).toContain("来源：The Guardian");
  });

  it("keeps license mechanics out of the product UI", () => {
    const html = renderToStaticMarkup(
      createElement(MusicContextCard, { context: featuredContext }),
    );

    expect(html).not.toContain("proprietary");
    expect(html).not.toContain("pitchfork.com/contact");
    expect(html).not.toContain("theguardian.com/help/terms-of-service");
  });

  it("can omit the repeated release identity in the desktop layout", () => {
    const CompactCard = MusicContextCard as ComponentType<{
      context: typeof featuredContext;
      showReleaseHeader: boolean;
    }>;
    const html = renderToStaticMarkup(
      createElement(CompactCard, {
        context: featuredContext,
        showReleaseHeader: false,
      }),
    );

    expect(html).not.toContain("album artwork");
    expect(html).not.toContain("<h2>Norman Fucking Rockwell!</h2>");
    expect(html).toContain("Singer-Songwriter");
  });

  it("omits an empty consensus block when only one source exists", () => {
    const context = {
      ...featuredContext,
      consensusBlocks: [
        {
          ...featuredContext.consensusBlocks[0]!,
          claims: [],
          skippedReason: "not enough sources",
        },
      ],
    };
    const html = renderToStaticMarkup(
      createElement(MusicContextCard, { context }),
    );

    expect(html).not.toContain('aria-label="综合归纳"');
  });
});
