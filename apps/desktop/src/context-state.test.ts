import { featuredContext } from "@linerfy/domain/fixtures";
import type { NowPlayingTrack } from "@linerfy/now-playing";
import { describe, expect, it } from "vitest";

import * as contextState from "./context-state";

const { contextStatusLabel, stageLabel, trackKey } = contextState;

function track(overrides: Partial<NowPlayingTrack> = {}): NowPlayingTrack {
  return {
    provider: "spotify",
    title: "Mariners Apartment Complex",
    artist: "Lana Del Rey",
    album: "Norman Fucking Rockwell!",
    state: "playing",
    ...overrides,
  };
}

describe("trackKey", () => {
  it("is stable for the same track", () => {
    expect(trackKey(track())).toBe(trackKey(track()));
  });

  it("changes when the album changes", () => {
    expect(
      trackKey(track({ album: "Chemtrails Over the Country Club" })),
    ).not.toBe(trackKey(track()));
  });

  it("changes when the provider URL changes", () => {
    expect(trackKey(track({ providerUrl: "spotify:track:1" }))).not.toBe(
      trackKey(track({ providerUrl: "spotify:track:2" })),
    );
  });
});

describe("stageLabel", () => {
  it("maps each pipeline stage to a concise label", () => {
    expect(stageLabel("resolve_entity")).toBe("识别专辑");
    expect(stageLabel("fetch_sources")).toBe("查找乐评来源");
    expect(stageLabel("build_source_summaries")).toBe("整理来源内容");
    expect(stageLabel("build_consensus")).toBe("生成综合归纳");
  });

  it("falls back to a generic label for an unknown stage", () => {
    expect(stageLabel("something-else")).toBe("处理中");
  });
});

describe("contextStatusLabel", () => {
  it("shows only the login requirement while signed out", () => {
    expect(contextStatusLabel("signed-out", { status: "loading" })).toBe(
      "登录后加载乐评",
    );
    expect(
      contextStatusLabel("signed-out", { status: "queued", stage: "x" }),
    ).toBe("登录后加载乐评");
  });

  it("distinguishes queued from running and labels the stage", () => {
    expect(
      contextStatusLabel("signed-in", {
        status: "queued",
        stage: "resolve_entity",
      }),
    ).toBe("排队中");
    expect(
      contextStatusLabel("signed-in", {
        status: "running",
        stage: "fetch_sources",
      }),
    ).toBe("查找乐评来源…");
  });

  it("marks a paused service instead of spinning", () => {
    expect(
      contextStatusLabel("signed-in", {
        status: "running",
        stage: "build_source_summaries",
        paused: true,
      }),
    ).toBe("整理来源内容…（服务暂停）");
  });

  it("returns the terminal labels directly", () => {
    expect(contextStatusLabel("signed-in", { status: "unavailable" })).toBe(
      "未找到乐评",
    );
    expect(contextStatusLabel("signed-in", { status: "ambiguous" })).toBe(
      "无法识别专辑",
    );
    expect(contextStatusLabel("signed-in", { status: "failed" })).toBe(
      "乐评获取失败",
    );
  });

  it("renders content while partial instead of a status label", () => {
    // A partial context is safe to show; the label must be null so the renderer
    // displays the context card (plus its stage note) rather than a loading
    // message. This is the polling-until-ready contract.
    const partial: contextState.ContextState = {
      status: "partial",
      context: featuredContext,
      stage: "build_consensus",
    };

    expect(contextStatusLabel("signed-in", partial)).toBeNull();
  });
});

describe("parseContextApiResponse", () => {
  it("accepts a partial response with a context", () => {
    const parsed = contextState.parseContextApiResponse({
      status: "partial",
      context: featuredContext,
      stage: "build_source_summaries",
    });

    expect(parsed.status).toBe("partial");
  });

  it("rejects a ready response that omits its context", () => {
    expect(() =>
      contextState.parseContextApiResponse({ status: "ready" }),
    ).toThrow();
  });
});
