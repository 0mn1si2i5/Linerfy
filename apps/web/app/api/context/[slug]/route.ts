import { featuredContext } from "@linerfy/domain/fixtures";
import { NextResponse } from "next/server";

const fixtureSlugs = new Set([
  "nfr",
  "norman-fucking-rockwell",
  "norman fucking rockwell",
]);

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  if (!fixtureSlugs.has(decodeURIComponent(slug).toLowerCase())) {
    return NextResponse.json({ code: "NOT_FOUND" }, { status: 404 });
  }

  return NextResponse.json(featuredContext, {
    headers: {
      "cache-control": "public, max-age=300, stale-while-revalidate=86400",
    },
  });
}
