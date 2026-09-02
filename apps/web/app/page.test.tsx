import { featuredContext } from "@linerfy/domain/fixtures";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { FeaturedContextResult } from "../lib/catalog";
import { HomePage } from "./home-page";

describe("Linerfy home page", () => {
  it("renders criticism with a route back to every source", () => {
    const result: FeaturedContextResult = {
      status: "ok",
      context: featuredContext,
    };
    const html = renderToStaticMarkup(createElement(HomePage, { result }));

    expect(html).toContain("Linerfy");
    expect(html).toContain("不替你播放");
    expect(html).toContain("只在你想知道时出现");
    expect(html).toContain("查看原文");
    expect(html).toContain("Pitchfork");
  });

  it("shows an explicit missing-coverage state when the release is not found", () => {
    const result: FeaturedContextResult = { status: "not-found" };
    const html = renderToStaticMarkup(createElement(HomePage, { result }));

    expect(html).toContain("这张专辑还没有被覆盖");
    expect(html).not.toContain("查看原文");
  });

  it("does not render a query failure as missing coverage", () => {
    const result: FeaturedContextResult = {
      status: "query-failed",
      message: "connection refused",
    };
    const html = renderToStaticMarkup(createElement(HomePage, { result }));

    expect(html).toContain("语境暂时无法加载");
    expect(html).not.toContain("这张专辑还没有被覆盖");
  });

  it("does not render invalid catalog data as missing coverage", () => {
    const result: FeaturedContextResult = {
      status: "invalid",
      message: "catalog is missing an artist or release",
    };
    const html = renderToStaticMarkup(createElement(HomePage, { result }));

    expect(html).toContain("语境数据异常");
    expect(html).not.toContain("这张专辑还没有被覆盖");
  });
});
