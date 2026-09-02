# Linerfy

> 在不打断听歌的前提下，提供可信、可追溯的音乐评论语境。
>
> Source-backed music criticism without interrupting the listening flow.

Linerfy 聚合专家与社区乐评、Genre 标签和有来源依据的中文总结。它不替代 Spotify 或 Apple Music，也不让模型脱离原文自行评价音乐。

Linerfy brings together professional and community criticism, genre labels, and source-backed Chinese summaries. It complements Spotify and Apple Music instead of replacing them, and never treats model output as an independent source of truth.

当前版本是用于验证核心体验的非商业脚手架：Web 是优先公开形态，Electron 是可手动分享给朋友的 macOS preview。项目目的与架构的中文说明见 [`docs/PRODUCT_AND_ARCHITECTURE.zh-CN.md`](docs/PRODUCT_AND_ARCHITECTURE.zh-CN.md)。

The current version is a non-commercial validation scaffold: the web is the primary public surface, while Electron provides a manually shared macOS friends preview. See the linked Chinese document for the product and architecture overview.

## 当前包含 / What is included

- Next.js Web 应用，可部署到 Vercel Hobby。A Next.js web app suitable for Vercel Hobby.
- 安全隔离的 Electron macOS preview，通过固定本地程序读取 Spotify 或 Apple Music 当前播放。A sandboxed Electron preview using fixed local programs for now-playing metadata.
- 共享的公开领域契约、UI 和 now-playing packages。Shared public domain, UI, and now-playing packages.
- Python 采集契约，验证来源策略、摘录限制和引用关系。Python ingestion contracts for source policy, excerpt limits, and provenance.
- Supabase 初始 schema，只公开已发布内容。A Supabase schema exposing published content only.

当前 fixture 用于证明完整链路，不代表已经启用生产抓取或模型调用。跨语言 schema 代码生成和 HTTP client 会在出现真实消费者后再引入。

The fixture proves the end-to-end contract; production crawling and model calls are not enabled. Cross-language schema generation and an HTTP client wait for real consumers.

## 本地运行 / Local setup

需要 Node.js 24、pnpm 11、Python 3.12 和 uv。Requires Node.js 24, pnpm 11, Python 3.12, and uv.

```bash
pnpm install
pnpm --filter @linerfy/web dev
```

在另一个终端启动 Electron preview / Start the Electron preview in another terminal:

```bash
pnpm --filter @linerfy/desktop dev
```

第一次读取 Spotify 或 Music 时，macOS 会请求 Automation 权限。应用只通过最小 preload bridge 接收当前曲目的元数据。

macOS requests Automation permission on first access. Only current-track metadata crosses the narrow preload bridge.

## 验证 / Verification

```bash
pnpm check
pnpm package:desktop
cd ingest
uv run ruff check .
uv run pytest
```

未签名 Electron 包输出到 `apps/desktop/out/`，仅用于与可信朋友手动分享。公开分发需要 Apple 签名与 notarization。

The unsigned Electron package is written to `apps/desktop/out/` for manual sharing with trusted friends. Public distribution requires Apple signing and notarization.

## 部署与范围 / Deployment boundary

Web 是第一公开形态，个人验证阶段使用 Vercel Hobby 和 Supabase Free。`.env.example` 只列变量名，真实值保存在本地或部署平台的 secrets 中。

The web is the first public surface, targeting Vercel Hobby and Supabase Free during personal validation. `.env.example` lists names only; real values stay in local or deployment secrets.

内容边界：采集端可私有保存全文用于生成总结，但公开网页/桌面端只展示 AI 总结、有限摘录、元数据与原文链接；全文不进入公开接口、前端或仓库。来源适配器（乐评网站与社区）是下一条可验证纵向切片；定时采集、模型调用、认证和补全请求队列仍不属于当前脚手架，随真实产品链路逐步加入。

Content boundary: the ingestion side may hold full text privately to produce summaries, but the public web/desktop surface shows only AI summaries, short excerpts, metadata, and original links; full text never reaches a public interface, frontend, or repository. Source adapters (review sites and communities) are the next verified slice; scheduled ingestion, model calls, authentication, and a coverage-request queue remain outside the scaffold.
