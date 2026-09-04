import { NextResponse, type NextRequest } from "next/server";

import { bearerToken, resolveAuthState } from "../../../lib/auth";
import { getContextBySlug } from "../../../lib/catalog";
import {
  nowPlayingRequestSchema,
  releaseSlug,
  requestFingerprint,
  toIngestPayload,
} from "../../../lib/request";
import { serviceClient } from "../../../lib/supabase";

export const dynamic = "force-dynamic";

// The authenticated online entry point: report the current track and receive
// its enrichment state (queued/running/ready/…), or the full context when ready.
export async function POST(request: NextRequest) {
  const token = bearerToken(request.headers.get("authorization"));
  if (!token) {
    return NextResponse.json(
      { error: "missing bearer token" },
      { status: 401 },
    );
  }
  const auth = await resolveAuthState(token);
  if (auth.status === "unauthenticated") {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }
  if (auth.status === "not-whitelisted") {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const parsed = nowPlayingRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid now-playing request", issues: parsed.error.issues },
      { status: 400 },
    );
  }

  const slug = releaseSlug(parsed.data.artist, parsed.data.album);
  const existing = await getContextBySlug(slug);
  if (existing.status === "ok") {
    return NextResponse.json({ status: "ready", context: existing.context });
  }
  if (existing.status === "query-failed" || existing.status === "invalid") {
    return NextResponse.json({ error: "context read failed" }, { status: 500 });
  }

  const fingerprint = requestFingerprint(parsed.data);
  const supabase = serviceClient();

  const { data: job, error: jobError } = await supabase
    .from("enrichment_jobs")
    .select("state, stage, resolution_status")
    .eq("entity_id", fingerprint)
    .maybeSingle();
  if (jobError) {
    return NextResponse.json({ error: "query failed" }, { status: 500 });
  }

  if (job) {
    if (job.state === "ready") {
      const result = await getContextBySlug(slug);
      if (result.status === "ok") {
        return NextResponse.json({ status: "ready", context: result.context });
      }
      // The job is marked ready but its context cannot be assembled — surface a
      // real failure rather than a bare `ready` the client would misread as
      // carrying a context.
      return NextResponse.json({ status: "failed", stage: job.stage });
    }
    // An entity that matched more than one release is a distinct, recoverable
    // state — never collapse it into `unavailable`.
    if (job.state === "unavailable" && job.resolution_status === "ambiguous") {
      return NextResponse.json({ status: "ambiguous" });
    }
    return NextResponse.json({ status: job.state, stage: job.stage });
  }

  const { error: insertError } = await supabase.from("enrichment_jobs").upsert(
    {
      entity_id: fingerprint,
      entity_kind: "release",
      payload: toIngestPayload(parsed.data),
      stage: "resolve_entity",
      state: "queued",
    },
    { onConflict: "entity_kind,entity_id", ignoreDuplicates: true },
  );
  if (insertError) {
    return NextResponse.json({ error: "queue failed" }, { status: 500 });
  }

  // Wake the Python worker immediately after a first insert. pg_net queues the
  // request asynchronously, so this never waits on the worker's response, and a
  // failure here is non-fatal: the one-minute cron still recovers the job.
  try {
    await supabase.rpc("wake_worker");
  } catch {
    // Ignore — the cron compensates for a missed wake.
  }

  return NextResponse.json({ status: "queued", stage: "resolve_entity" });
}
