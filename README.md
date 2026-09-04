# Linerfy

> 依附于正在播放的音乐的 macOS 乐评 companion。不打断听歌，只在你想了解时出现。
>
> A macOS music-criticism companion that sits next to what is playing. It never interrupts listening; it surfaces context only when you want it.

Linerfy 在你用 Spotify 或 Apple Music 听歌时识别当前曲目，并在一个轻量的菜单栏窗口里展示曲风、相关标签、来源评分、单来源中文总结、跨来源综合观点和原文链接。只有你想深入了解时才离开 Linerfy 前往原始来源。

Linerfy identifies the current track while you listen on Spotify or Apple Music, and shows genres, tags, source ratings, per-source Chinese summaries, cross-source consensus, and original links in a lightweight menu-bar window. You leave Linerfy for the original source only when you want to go deeper.

v1 不建设搜索、内容首页、推荐、收藏、社交、评论、播放历史或独立音乐浏览体验。

v1 ships no search, content home, recommendations, favorites, social features, comments, play history, or standalone music browsing.

## 形态 / Shape

- **macOS companion**（`apps/desktop`）：菜单栏 popover 与全局快捷键打开，读取当前播放、完成 GitHub OAuth 登录，并展示完整语境（曲风/标签/评分/单来源总结/综合观点/引用/链接）。
- **Vercel API**（`apps/web`）：已认证 API（`POST /api/context` 在线创建任务 + `/api/context/[slug]` 读语境）、GitHub OAuth 回调、说明网页，以及受保护的 worker route（`/api/enrichment/run`，由 Supabase Cron 每分钟调用）。说明网页不读取当前播放，也不提供搜索。
- **采集**（`ingest`）：实体匹配、许可来源、模型总结的批处理管线。
- **存储**（`supabase/migrations`）：catalog、enrichment jobs 与行级权限。

## 正式数据来源 / Authorized sources

v1 默认启用的来源仅包括：MusicBrainz、Wikidata、CritiqueBrainz、Wikipedia（仅 MediaWiki API 的 Reception / Critical reception 内容）。

The only v1 sources are MusicBrainz, Wikidata, CritiqueBrainz, and Wikipedia (Reception via the MediaWiki API).

Guardian、Pitchfork、Album of the Year、Metacritic、Rate Your Music、Reddit 等没有适当自动化授权或许可不清晰的来源不属于正式 v1：不开发绕过限制的抓取器；旧 Guardian adapter 仅作参考保留并默认关闭，不进入生产流水线。

Guardian, Pitchfork, AOTY, Metacritic, RYM, Reddit, and other unlicensed or unauthorized sources are not part of v1: no bypass scrapers, and the legacy Guardian adapter is kept reference-only and disabled by default.

## 认证与隐私 / Auth & privacy

- 登录使用 Supabase Auth 的 GitHub OAuth，并以 GitHub 数字用户 ID 校验 Vercel 环境变量白名单。
- catalog 与内容 API 仅允许已登录且在白名单内的用户访问；取消匿名 Supabase catalog 读取。
- macOS 登录完成后把 session/refresh token 存入 Keychain；renderer 只得到最小登录状态，不接触长期令牌或服务端密钥。
- service-role、来源 API key、模型 key 只存在于服务端或 ingestion/worker 环境。
- 不保存连续播放历史；日志只记录任务 ID、阶段、耗时、provider、token usage、错误分类和时间，不含全文、prompt、密钥或播放历史。

Auth uses Supabase Auth GitHub OAuth, gated by a numeric GitHub ID whitelist in Vercel env. Catalog and content APIs are available only to logged-in, whitelisted users; anonymous catalog reads are removed. The macOS app stores session/refresh tokens in Keychain; the renderer only sees minimal login state. No continuous play history is kept, and logs never contain full text, prompts, secrets, or play history.

## 本地运行 / Local setup

需要 Node.js 24、pnpm 11、Python 3.12 和 uv。Requires Node.js 24, pnpm 11, Python 3.12, and uv.

```bash
pnpm install
pnpm --filter @linerfy/desktop dev   # macOS companion
pnpm --filter @linerfy/web dev       # API + OAuth + smoke
```

打包并打开桌面版：

```bash
pnpm package:desktop
open "apps/desktop/out/Linerfy-darwin-arm64/Linerfy.app"
```

桌面构建会把 Supabase URL、publishable key 和 Web API URL 作为公开客户端配置写入应用；service-role、模型 key 和 worker secret 永不进入桌面包。打开后点菜单栏里的 Linerfy 图标，或按 `⌘⇧L`。网页不会也不能直接读取 macOS 播放器。

Build and open the desktop app with the commands above. The build embeds only public client configuration (Supabase URL, publishable key, and Web API URL); server and model secrets never enter the app. Open it from the menu bar or press `⌘⇧L`. The website does not read macOS playback directly.

第一次读取 Spotify 或 Music 时，macOS 会请求 Automation 权限。应用只通过最小 preload bridge 接收当前曲目的元数据，播放器元数据始终视为不可信输入。

macOS requests Automation permission on first access. Only current-track metadata crosses the narrow preload bridge; player metadata is always treated as untrusted input.

## 采集与运行命令 / Ingestion & admin

无参数运行只显示帮助并退出，绝不写数据库。Running with no arguments prints help and exits, never writing.

```bash
cd ingest
python -m linerfy_ingest --run-enrichment   # 运行一个 worker tick
python -m linerfy_ingest --pause            # 全局暂停模型生成
python -m linerfy_ingest --resume           # 恢复模型生成
python -m linerfy_ingest --jobs             # 列出 enrichment 队列
python -m linerfy_ingest --retry-failed     # 重新入队失败任务
python -m linerfy_ingest --purge            # 清理过期私有正文
```

## 验证 / Verification

```bash
pnpm check
pnpm --filter @linerfy/desktop package   # 生成本地 Electron 包
cd ingest
uv run ruff check .
uv run pytest
```

未签名 Electron 包输出到 `apps/desktop/out/`，仅用于手动分享与边界验证。公开分发需要 Apple 签名与 notarization（v1 不实现）。

The unsigned Electron package is written to `apps/desktop/out/` for manual sharing and boundary verification. Public distribution requires Apple signing and notarization (not in v1).

## 当前状态 / Status

> 以下标注依据 fresh 验证（测试 + 类型检查 + 构建 + 代码路径），不代表生产联调通过。

- **代码路径完成且有测试**：Supabase catalog 与 RLS（取消匿名读取）；公开说明页与已认证 `/context/[slug]`、service-role 仅在服务端；可追溯中文总结（模型边界、按 scope 原子发布、claim 引用）；多 provider 协议（OpenAI 兼容 + Anthropic）；许可证池隔离（CritiqueBrainz=CC BY-NC-SA 3.0、Wikipedia=CC BY-SA 4.0，各自成池不混）；可靠 100 元预算账本（按模型费率、预检 + 结算、未知模型 fail-closed）；DB 测试双重守卫与隔离实体；MusicBrainz/Wikidata/Cover Art Archive 实体适配器；CritiqueBrainz/Wikipedia Reception 语料适配器（含 SourcePolicy）；enrichment 四阶段真实 worker（`resolve_entity → fetch_sources → build_source_summaries → build_consensus`）与状态机、管理 CLI；在线任务创建与受保护 worker route；macOS 菜单栏 now-playing 识别、GitHub OAuth 登录、Keychain token 存储与完整 context 展示。
- **生产基础设施与 Web OAuth 已联调**：生产 Supabase 迁移、Vercel Web/worker、Vault 与定时 worker 已配置；GitHub OAuth 的浏览器登录已于 2026-09-04 复验通过。桌面 OAuth 仍需用重新打包的 `.app` 做一次人工回环验证。

细节见 [`docs/PRODUCT_AND_ARCHITECTURE.zh-CN.md`](docs/PRODUCT_AND_ARCHITECTURE.zh-CN.md)。
