import { LinerfyMark } from "@linerfy/ui";
import Link from "next/link";

export function HomePage() {
  return (
    <main className="app-shell">
      <header className="app-bar">
        <div className="brand">
          <LinerfyMark />
          <span>Linerfy</span>
        </div>
        <Link className="button secondary" href="/login">
          登录
        </Link>
      </header>

      <section className="status-list" aria-label="Linerfy 状态">
        <div className="status-row">
          <span>桌面端</span>
          <span className="status-value">macOS</span>
        </div>
        <div className="status-row">
          <span>当前播放</span>
          <span className="status-value">由桌面端读取</span>
        </div>
        <div className="status-row">
          <span>网页端</span>
          <span className="status-value">认证与 API</span>
        </div>
      </section>
    </main>
  );
}
