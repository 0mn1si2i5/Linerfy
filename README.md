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
- Python 采集与总结：The Guardian 官方 API adapter、可追溯中文总结（DeepSeek）、来源策略与摘录限制。Python ingestion and summarization: a Guardian Content API adapter, traceable Chinese summaries (DeepSeek), source policy, and excerpt limits.
- Supabase 初始 schema，只公开已发布内容。A Supabase schema exposing published content only.

## 真实内容链路 / The real content chain

第一条真实链路已打通：Guardian 官方 API 抓取一篇乐评 → 正文私有入库（`review_document_bodies`，匿名不可读）→ DeepSeek 生成带引用的中文总结 → Supabase → Web 服务端读取并展示。

The first real chain works end to end: the Guardian Content API fetches a review → the full body is stored privately (`review_document_bodies`, unreadable by anon) → DeepSeek produces a source-citing Chinese summary → Supabase → the web reads and renders it.

尚未打通的部分：Pitchfork 仍是手写 fixture（无真实抓取）；社区语料尚未接入；Web 当前只展示第一条 claim 作为「中文共识」。正文的 30 天保留策略已记录在 source policy 中，但尚未自动执行。

Not yet connected: Pitchfork is still a hand-written fixture (no real fetch); community sources are not yet wired; the web currently renders only the first claim as the "consensus". The 30-day body-retention policy is recorded in source policy but is not yet enforced automatically.

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

## 采集与总结命令 / Ingestion commands

无参数运行只显示帮助并退出，绝不写数据库。Running with no arguments prints help and exits, never writing.

```bash
cd ingest

# 真实采集：抓取卫报一篇乐评并写入（正文私有）。需要 GUARDIAN_API_KEY。
# Fetch one Guardian review (private body). Requires GUARDIAN_API_KEY.
python -m linerfy_ingest --guardian <article-path>

# 真实总结：读取已入库正文，调用 DeepSeek 生成可追溯总结，原子写入。
# Summarize published bodies into traceable claims, written atomically. Requires MODEL_API_KEY.
python -m linerfy_ingest --summarize <release-slug>

# fixture 仅用于本地/标记测试库，且只 insert-only、不覆盖已存在记录。
# The fixture is test-only: it refuses remote databases and never overwrites.
LINERFY_RESET_ALLOWED=1 python -m linerfy_ingest --fixture
```

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

Web 是第一公开形态，个人验证阶段使用 Vercel Hobby 和 Supabase Free。`.env.example` 只列变量名（含 `GUARDIAN_API_KEY`、`MODEL_API_KEY`），真实值保存在本地或部署平台的 secrets 中。

The web is the first public surface, targeting Vercel Hobby and Supabase Free during personal validation. `.env.example` lists names only (including `GUARDIAN_API_KEY` and `MODEL_API_KEY`); real values stay in local or deployment secrets.

内容边界：采集端可私有保存全文用于生成总结，但公开网页/桌面端只展示 AI 总结、有限摘录、元数据与原文链接；全文不进入公开接口、前端或仓库。定时采集、认证和补全请求队列仍不属于当前脚手架，随真实产品链路逐步加入。

Content boundary: the ingestion side may hold full text privately to produce summaries, but the public web/desktop surface shows only AI summaries, short excerpts, metadata, and original links; full text never reaches a public interface, frontend, or repository. Scheduled ingestion, authentication, and a coverage-request queue remain outside the scaffold.
