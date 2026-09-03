import { NextResponse, type NextRequest } from "next/server";

import { bearerToken } from "../../../../lib/auth";
import { serviceClient } from "../../../../lib/supabase";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// The worker tick. Protected by a separate worker secret; does a bounded amount
// of DB maintenance (reaping timed-out jobs). The heavy five-stage enrichment
// runs in the Python worker (`python -m linerfy_ingest --run-enrichment`).
export async function POST(request: NextRequest) {
  const secret = process.env.LINERFY_WORKER_SECRET;
  if (!secret) {
    return NextResponse.json({ error: "worker not configured" }, { status: 503 });
  }
  const token = bearerToken(request.headers.get("authorization"));
  if (!token || token !== secret) {
    return NextResponse.json({ error: "forbidden" }, { status: 401 });
  }

  const supabase = serviceClient();
  const { data, error } = await supabase.rpc("reap_enrichment_timeouts");
  if (error) {
    return NextResponse.json({ error: "reap failed" }, { status: 500 });
  }
  return NextResponse.json({ reaped: data ?? 0 });
}
