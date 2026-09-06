import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { featuredContext } from "@linerfy/domain/fixtures";
import { MusicContextCard } from "@linerfy/ui";

it("renders both license pools from the same provider without duplicate provider cards", () => {
  const original = featuredContext.sourceSummaries[0]!;
  const first = {
    ...original,
    claims: [
      {
        id: "one",
        text: "第一许可池内容",
        sourceIds: [featuredContext.sources[0]!.id],
      },
    ],
  };
  const second = {
    ...first,
    license: {
      id: "CC BY-SA 4.0",
      url: "https://creativecommons.org/licenses/by-sa/4.0/",
    },
    claims: [{ ...first.claims[0]!, id: "two", text: "第二许可池内容" }],
  };
  const html = renderToStaticMarkup(
    <MusicContextCard
      context={{
        ...featuredContext,
        sources: [featuredContext.sources[0]!],
        sourceSummaries: [first, second],
        consensusBlocks: [],
      }}
    />,
  );
  expect(html).toContain("第一许可池内容");
  expect(html).toContain("第二许可池内容");
  expect(html.match(/provider-card/g)).toHaveLength(1);
});
