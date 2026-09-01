# Linerfy

Linerfy is a lightweight companion for music criticism: expert reviews, community context, genres, and source-backed Chinese summaries without replacing the user's music player.

This repository starts with a working fixture rather than production crawling or model calls. Every displayed summary claim points back to a stored source, and public review content is limited to metadata, short excerpts or paraphrases, and original links.

## What is included

- A Next.js web app suitable for an early Vercel Hobby deployment.
- An Electron macOS friends preview that reads Spotify or Apple Music through fixed local automation programs.
- Shared domain, UI, API-client, and now-playing packages.
- A Python ingestion contract with source-policy and provenance validation.
- A normalized Supabase migration with published-content row-level policies.

## Local setup

Prerequisites are Node.js 24, pnpm 11, Python 3.12, and uv.

```bash
pnpm install
pnpm --filter @linerfy/web dev
```

Open the Electron preview in another terminal:

```bash
pnpm --filter @linerfy/desktop dev
```

macOS will ask for Automation permission the first time the preview reads Spotify or Music. The app receives only current-track metadata through a narrow preload bridge.

## Verification

```bash
pnpm check
pnpm package:desktop
cd ingest
uv run ruff check .
uv run pytest
```

The unsigned Electron package is written under `apps/desktop/out/` and is intended only for manual sharing with trusted friends. Public macOS distribution would require Apple code signing and notarization.

## Deployment boundary

The web app is the first public surface. During personal validation it targets Vercel Hobby and Supabase Free. Environment variable names are listed in `.env.example`; real values stay in local or deployment secrets.

Production source adapters, scheduled ingestion, model calls, authentication, and coverage-request rate limiting are deliberately not part of this initial scaffold.
