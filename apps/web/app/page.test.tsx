import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it } from "vitest";

import Page from "./page";

describe("Linerfy home page", () => {
  it("renders criticism with a route back to every source", () => {
    const html = renderToStaticMarkup(createElement(Page));

    expect(html).toContain("Linerfy");
    expect(html).toContain("不替你播放");
    expect(html).toContain("只在你想知道时出现");
    expect(html).toContain("查看原文");
    expect(html).toContain("Pitchfork");
  });
});
