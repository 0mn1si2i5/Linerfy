import { featuredContext } from "@linerfy/domain/fixtures";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { HomePage } from "./home-page";

describe("Linerfy home page", () => {
  it("renders criticism with a route back to every source", () => {
    const html = renderToStaticMarkup(
      createElement(HomePage, { context: featuredContext }),
    );

    expect(html).toContain("Linerfy");
    expect(html).toContain("不替你播放");
    expect(html).toContain("只在你想知道时出现");
    expect(html).toContain("查看原文");
    expect(html).toContain("Pitchfork");
  });

  it("shows an explicit missing-coverage state when there is no context", () => {
    const html = renderToStaticMarkup(
      createElement(HomePage, { context: null }),
    );

    expect(html).toContain("这张专辑还没有被覆盖");
    expect(html).not.toContain("查看原文");
  });
});
