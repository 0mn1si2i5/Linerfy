import { LinerfyMark } from "@linerfy/ui";
import type { NowPlayingTrack } from "@linerfy/now-playing";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import "./renderer.css";

type ViewState =
  | { kind: "loading" }
  | { kind: "no-playback" }
  | { kind: "playing"; track: NowPlayingTrack };

function DesktopApp() {
  const [view, setView] = useState<ViewState>({ kind: "loading" });
  const [locked, setLocked] = useState(true);

  useEffect(() => {
    let mounted = true;

    // Initial read, then the main process pushes updates while the window is open.
    void window.linerfy.getNowPlaying().then((track) => {
      if (mounted)
        setView(track ? { kind: "playing", track } : { kind: "no-playback" });
    });
    const stopNowPlaying = window.linerfy.onNowPlayingChanged((track) => {
      setView(track ? { kind: "playing", track } : { kind: "no-playback" });
    });

    void window.linerfy
      .getWindowState()
      .then((state) => setLocked(state.locked));
    const stopWindowState = window.linerfy.onWindowStateChanged((state) =>
      setLocked(state.locked),
    );

    return () => {
      mounted = false;
      stopNowPlaying();
      stopWindowState();
    };
  }, []);

  return (
    <main className="companion">
      <header className="companion-header">
        <span className="brand">
          <LinerfyMark /> Linerfy
        </span>
        <button
          className="lock-toggle"
          type="button"
          title={locked ? "解锁为普通窗口" : "重新锁定为菜单栏窗口"}
          onClick={() => void window.linerfy.setWindowLocked(!locked)}
        >
          {locked ? "解锁" : "锁定"}
        </button>
      </header>

      {view.kind === "loading" ? (
        <p className="now-playing muted">正在读取…</p>
      ) : view.kind === "no-playback" ? (
        <p className="now-playing muted">当前没有播放音乐</p>
      ) : (
        <div className="track">
          <p className="now-playing">
            {view.track.title} — {view.track.artist}
          </p>
          <p className="track-meta">
            {view.track.album} ·{" "}
            {view.track.provider === "spotify" ? "Spotify" : "Apple Music"} ·{" "}
            {view.track.state === "playing" ? "正在播放" : "已暂停"}
          </p>
        </div>
      )}
    </main>
  );
}

const root = document.getElementById("root");
if (!root) throw new Error("Missing desktop root element");
createRoot(root).render(
  <StrictMode>
    <DesktopApp />
  </StrictMode>,
);
