import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// This is NOT the enrichment worker. The real worker is the deployable Python
// function at `ingest/api/enrichment.py` (the Worker Vercel Project), which
// Supabase Cron invokes. This route survives only as an explicit health check
// so a stray caller learns the worker moved rather than being silently reaped.

export async function GET() {
  return NextResponse.json({
    ok: true,
    worker: "POST /api/enrichment (Python function, Worker Vercel Project)",
  });
}

export async function POST(_request: NextRequest) {
  return NextResponse.json(
    {
      error: "worker moved",
      detail: "enrichment runs in the Python function, not this route",
    },
    { status: 410 },
  );
}
