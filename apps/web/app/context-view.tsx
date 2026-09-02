import { MusicContextCard } from "@linerfy/ui";

import type { ContextResult } from "../lib/catalog";

/**
 * Renders the shared context card, or the right state for a missing, failing,
 * or invalid read. Only `not-found` reads as "not covered yet".
 */
export function ContextView({ result }: { result: ContextResult }) {
  switch (result.status) {
    case "ok":
      return <MusicContextCard context={result.context} />;
    case "not-found":
      return <p className="empty-state">这张专辑还没有被覆盖。</p>;
    case "query-failed":
      return <p className="empty-state">语境暂时无法加载，请稍后再试。</p>;
    case "invalid":
      return <p className="empty-state">语境数据异常，请稍后再试。</p>;
  }
}
