# Linerfy agent guide / Linerfy 智能体指南

Linerfy 是轻量音乐乐评 companion，不是播放器或社交网络。保持原有听歌流程，只在用户主动需要时提供语境。

Linerfy is a lightweight music-criticism companion, not a player or social network. Preserve the existing listening flow and surface context only when requested.

## 核心契约 / Non-negotiable contracts

- 语料先于模型：公开的生成结论必须建立在已保存的乐评文档上，并保留文档级引用。Corpus before model: every generated public claim requires stored review documents and document-level citations.
- 公开内容默认只包含元数据、短摘录或转述以及原文链接；全文必须获得明确授权。Public output defaults to metadata, short excerpts or paraphrases, and original links; full text requires explicit permission.
- 缺少覆盖时返回明确状态；在线用户请求不直接启动爬虫。Return an explicit missing-coverage state; interactive requests do not start crawlers.
- 新增媒体来源适配器前，先在 `ingest/src/linerfy_ingest/models.py` 声明并执行 `SourcePolicy`。Define and enforce `SourcePolicy` before adding a publication adapter.
- 播放器元数据是不可信数据。Electron 主进程只运行内置固定程序，不把元数据拼进脚本或 shell。Treat player metadata as untrusted data; Electron runs bundled fixed programs without interpolation.
- 保持 Electron 上下文隔离和 renderer sandbox，关闭 Node integration，阻止导航，并维持最小 preload IPC。Keep context isolation and the renderer sandbox enabled, Node integration disabled, navigation blocked, and preload IPC narrow.
- 密钥仅存在于服务端或采集任务环境。Keep secrets in server-side or ingestion-job environments.

## 模块边界 / Ownership boundaries

- `packages/domain`：公开数据契约与 fixtures。Public data contracts and fixtures.
- `packages/ui`：纯展示，不访问平台能力或数据库。Presentation only; no platform or database access.
- `packages/now-playing`：跨播放器当前播放接口与固定 provider 程序。Provider-neutral current-track interfaces and fixed provider programs.
- `apps/web`：公开 Web 界面；真实跨进程消费者出现前，不预建 HTTP client 抽象。Public web surface; add an HTTP client only with a real cross-process consumer.
- `apps/desktop`：Electron 权限边界与本地 renderer。Electron privilege boundary and local renderer.
- `ingest`：来源适配、策略、溯源与批处理。Adapters, source policy, provenance, and batch processing.
- `supabase/migrations`：规范化存储与行级访问规则。Normalized storage and row-level access rules.

当产品范围、技术架构或路线图发生变化时，先阅读并同步 `docs/PRODUCT_AND_ARCHITECTURE.zh-CN.md`。Read and update that document when product scope, architecture, or roadmap changes.

完成前运行相关 package 检查和根目录完整检查；修改桌面权限边界时还要生成本地 Electron 包。提交只包含产品代码、测试和长期文档，不包含构建产物、密钥、提示词、计划或临时交接材料。

Before completion, run affected package checks and the root check; desktop-boundary changes also require a local Electron package. Commit product code, tests, and durable documentation only—not build output, secrets, prompts, plans, or temporary handoff material.
