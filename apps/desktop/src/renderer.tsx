import { LinerfyMark, MusicContextCard } from "@linerfy/ui";
import type { NowPlayingTrack } from "@linerfy/now-playing";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import type { LoginState } from "./auth-state";
import type { ContextState } from "./context-state";
import "./renderer.css";

type ViewState =
  | { kind: "loading" }
  | { kind: "no-playback" }
  | { kind: "playing"; track: NowPlayingTrack };

function DesktopApp() {
  const [view, setView] = useState<ViewState>({ kind: "loading" });
  const [locked, setLocked] = useState(true);
  const [auth, setAuth] = useState<LoginState>({ status: "signed-out" });
  const [signingIn, setSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [context, setContext] = useState<ContextState>({ status: "idle" });

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

    void window.linerfy.getAuthState().then((state) => {
      if (mounted) setAuth(state);
    });
    const stopAuthState = window.linerfy.onAuthStateChanged((state) =>
      setAuth(state),
    );

    const stopContext = window.linerfy.onContextChanged((state) =>
      setContext(state),
    );

    return () => {
      mounted = false;
      stopNowPlaying();
      stopWindowState();
      stopAuthState();
      stopContext();
    };
  }, []);

  async function handleSignIn() {
    setSigningIn(true);
    setAuthError(null);
    const result = await window.linerfy.signIn();
    setSigningIn(false);
    if (result.status === "error") setAuthError(result.message);
    // On success the main process broadcasts auth:state, which updates `auth`.
  }

  return (
    <main className="companion">
      <header className="companion-header">
        <span className="brand">
          <LinerfyMark /> Linerfy
        </span>
        <div className="header-actions">
          {auth.status === "signed-in" ? (
            <button
              className="auth-toggle"
              type="button"
              title="退出登录"
              onClick={() => void window.linerfy.signOut()}
            >
              已登录
            </button>
          ) : (
            <button
              className="auth-toggle"
              type="button"
              title="使用 GitHub 登录"
              disabled={signingIn}
              onClick={() => void handleSignIn()}
            >
              {signingIn ? "登录中…" : "登录"}
            </button>
          )}
          <button
            className="lock-toggle"
            type="button"
            title={locked ? "解锁为普通窗口" : "重新锁定为菜单栏窗口"}
            onClick={() => void window.linerfy.setWindowLocked(!locked)}
          >
            {locked ? "解锁" : "锁定"}
          </button>
        </div>
      </header>

      {authError ? (
        <p className="auth-error" role="alert">
          {authError}
        </p>
      ) : null}

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

      {context.status === "ready" ? (
        <div className="context">
          <MusicContextCard context={context.context} />
        </div>
      ) : context.status === "queued" || context.status === "running" ? (
        <p className="context-status muted">正在生成语境…</p>
      ) : context.status === "unavailable" ? (
        <p className="context-status muted">暂无可用语境</p>
      ) : context.status === "failed" ? (
        <p className="context-status muted">语境生成失败</p>
      ) : context.status === "error" ? (
        <p className="context-status error">{context.message}</p>
      ) : context.status === "loading" ? (
        <p className="context-status muted">正在读取语境…</p>
      ) : null}
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
