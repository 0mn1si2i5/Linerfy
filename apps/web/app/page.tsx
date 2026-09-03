"use client";

import { FEATURED_SLUG } from "../lib/constants";

import { HomePage } from "./home-page";
import { useAuthenticatedContext } from "./use-authenticated-context";

// The home smoke page requires an authenticated, whitelisted session: the
// context is fetched through /api/context/[slug], never via a direct
// service-role read.
export default function Page() {
  const state = useAuthenticatedContext(FEATURED_SLUG);

  if (state.status === "loading") {
    return (
      <main>
        <p className="empty-state">正在加载…</p>
      </main>
    );
  }
  if (state.status === "unauthenticated") {
    return (
      <main>
        <p className="empty-state">
          请先 <a href="/login">登录</a> 后查看乐评语境。
        </p>
      </main>
    );
  }
  if (state.status === "error") {
    return (
      <main>
        <p className="empty-state">语境暂时无法加载。</p>
      </main>
    );
  }
  return <HomePage result={state.result} />;
}
