# Linerfy agent guide

Linerfy is a lightweight criticism companion, not a music player or social network. Keep the listening flow outside Linerfy; surface context only when requested.

## Non-negotiable contracts

- Corpus before model: no generated public claim may exist without stored review documents.
- Every summary claim must retain document-level citations. Default public output is metadata, short excerpts or paraphrases, and original links. Full text requires explicit permission.
- A user request may enqueue missing coverage but must never synchronously start a crawler.
- Each publication adapter must declare and enforce `SourcePolicy` in `ingest/src/linerfy_ingest/models.py` before it fetches anything.
- Treat player metadata as untrusted data. The Electron main process may run only bundled, fixed automation programs; never interpolate metadata into script or shell source.
- Keep `contextIsolation` and the renderer sandbox enabled, Node integration disabled, navigation blocked, and preload IPC narrow.
- Keep secrets out of browser and Electron renderer bundles.

## Ownership boundaries

- `packages/domain`: canonical public contracts and fixtures.
- `packages/ui`: presentation only; no platform or database access.
- `packages/api-client`: validated, read-oriented API access.
- `packages/now-playing`: provider-neutral current-track interfaces and fixed provider programs.
- `apps/web`: public Next.js surface and HTTP boundary.
- `apps/desktop`: Electron privilege boundary and local renderer.
- `ingest`: adapters, source policy, provenance, and batch processing.
- `supabase/migrations`: normalized storage and row-level access rules.

Before claiming completion, run the relevant package checks plus the root check. For desktop-boundary changes, also produce a local Electron package. Do not commit generated output, credentials, or process-only planning documents.
