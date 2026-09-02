import { LinerfyMark } from "@linerfy/ui";
import Link from "next/link";

import { getContextBySlug } from "../../../lib/catalog";
import { ContextView } from "../../context-view";

// Reads live catalog data on every request; never prerendered.
export const dynamic = "force-dynamic";

export default async function Page({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const result = await getContextBySlug(slug);

  return (
    <main>
      <nav className="site-nav" aria-label="Main navigation">
        <Link className="brand" href="/">
          <LinerfyMark />
          <span>Linerfy</span>
        </Link>
        <span className="preview-pill">EARLY LISTENING</span>
      </nav>

      <section className="featured">
        <div className="featured-intro">
          <p className="eyebrow">CONTEXT</p>
          <p>
            <Link href="/">← 返回</Link>
          </p>
        </div>
        <ContextView result={result} />
      </section>
    </main>
  );
}
