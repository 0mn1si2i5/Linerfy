import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { HomePage } from "./home-page";

describe("Linerfy home page", () => {
  it("shows only operational status and no search or marketing copy", () => {
    const html = renderToStaticMarkup(createElement(HomePage));

    expect(html).toContain("Linerfy");
    expect(html).toContain("当前播放");
    expect(html).toContain("由桌面端读取");
    expect(html).toContain("认证与 API");
    expect(html).not.toContain("<form");
    expect(html).not.toContain("搜索歌曲");
    expect(html).not.toContain("想多知道");
  });
});
