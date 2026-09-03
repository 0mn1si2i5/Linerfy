import { NextResponse, type NextRequest } from "next/server";

import { bearerToken, resolveAuthState } from "../../../../lib/auth";
import { getContextBySlug } from "../../../../lib/catalog";

// The single authenticated machine boundary for reading a release's context.
// Only a whitelisted GitHub identity may read the catalog; pages and clients
// reach the catalog exclusively through here, never via a direct service-role
// read.
export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;

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

  const result = await getContextBySlug(slug);
  switch (result.status) {
    case "ok":
      return NextResponse.json({ status: "ok", context: result.context });
    case "not-found":
      return NextResponse.json({ status: "not-found" }, { status: 404 });
    case "query-failed":
      return NextResponse.json(
        { status: "query-failed", message: result.message },
        { status: 500 },
      );
    case "invalid":
      return NextResponse.json(
        { status: "invalid", message: result.message },
        { status: 500 },
      );
  }
}
