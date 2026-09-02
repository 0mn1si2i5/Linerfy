import { NextResponse, type NextRequest } from "next/server";

import { getContextBySlug } from "../../../../lib/catalog";
import { resolveAuthState } from "../../../../lib/auth";

// The authenticated machine boundary for reading a release's context. Only a
// whitelisted GitHub identity may read the catalog; anonymous reads are gone.
export const dynamic = "force-dynamic";

function bearerToken(request: NextRequest): string {
  const header = request.headers.get("authorization") ?? "";
  return header.startsWith("Bearer ")
    ? header.slice("Bearer ".length).trim()
    : "";
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;

  const token = bearerToken(request);
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
