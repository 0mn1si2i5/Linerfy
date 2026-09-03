"use client";

import { LinerfyMark } from "@linerfy/ui";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ContextView } from "../../context-view";
import { useAuthenticatedContext } from "../../use-authenticated-context";

// Requires an authenticated, whitelisted session; the context is fetched
// through the authenticated API, never via a direct service-role read.
export default function Page() {
  const params = useParams<{ slug: string }>();
  const state = useAuthenticatedContext(params.slug);

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
        {state.status === "loading" ? (
          <p className="empty-state">正在加载…</p>
        ) : state.status === "unauthenticated" ? (
          <p className="empty-state">
            请先 <a href="/login">登录</a> 后查看乐评语境。
          </p>
        ) : state.status === "error" ? (
          <p className="empty-state">语境暂时无法加载。</p>
        ) : (
          <ContextView result={state.result} />
        )}
      </section>
    </main>
  );
}
