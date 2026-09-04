import { MusicContextCard } from "@linerfy/ui";
import type { NowPlayingTrack } from "@linerfy/now-playing";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import type { LoginState } from "./auth-state";
import { contextStatusLabel, type ContextState } from "./context-state";
import "./renderer.css";

function formatTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

type ViewState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "no-playback" }
  | { kind: "playing"; track: NowPlayingTrack };

function DesktopApp() {
  const [view, setView] = useState<ViewState>({ kind: "loading" });
  const [locked, setLocked] = useState(true);
  const [auth, setAuth] = useState<LoginState>({ status: "signed-out" });
  const [signingIn, setSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [context, setContext] = useState<ContextState>({ status: "idle" });
  const [scrubPosition, setScrubPosition] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;

    // Initial read, then the main process pushes updates while the window is open.
    void window.linerfy
      .getNowPlaying()
      .then((track) => {
        if (mounted)
          setView(track ? { kind: "playing", track } : { kind: "no-playback" });
      })
      .catch(() => {
        if (mounted) setView({ kind: "error" });
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

  const playingTrack = view.kind === "playing" ? view.track : null;
  const releaseYear =
    context.status === "ready" || context.status === "partial"
      ? context.context.release.year
      : null;
  const contextLabel = playingTrack
    ? contextStatusLabel(auth.status, context)
    : null;

  const durationMs = playingTrack?.durationMs;
  const positionMs = playingTrack?.positionMs;
  const showProgress = durationMs !== undefined && positionMs !== undefined;
  const scrubValue = scrubPosition ?? positionMs ?? 0;

  function commitSeek() {
    if (scrubPosition !== null) {
      void window.linerfy.seekTo(scrubPosition);
      setScrubPosition(null);
    }
  }

  return (
    <main className="companion">
      <header className="companion-header">
        <span className="brand">Linerfy</span>
        <div className="header-actions">
          {auth.status === "signed-in" ? (
            <button
              className="auth-toggle"
              type="button"
              title="退出登录"
              onClick={() => void window.linerfy.signOut()}
            >
              已连接
            </button>
          ) : (
            <button
              className="auth-toggle"
              type="button"
              title="使用 GitHub 登录"
              disabled={signingIn}
              onClick={() => void handleSignIn()}
            >
              {signingIn ? "连接中…" : "连接"}
            </button>
          )}
          <button
            className="lock-toggle"
            type="button"
            title={locked ? "允许移动和调整大小" : "锁定当前位置和大小"}
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
        <p className="now-playing muted">读取当前播放…</p>
      ) : view.kind === "error" ? (
        <p className="now-playing muted">无法读取当前播放</p>
      ) : view.kind === "no-playback" ? (
        <p className="now-playing muted">未检测到正在播放的音乐</p>
      ) : playingTrack ? (
        <>
          <section className="album-context" aria-label="当前专辑">
            {playingTrack.artworkUrl ? (
              <img
                className="album-artwork"
                src={playingTrack.artworkUrl}
                alt={`${playingTrack.album} 封面`}
                referrerPolicy="no-referrer"
              />
            ) : null}
            <div className="album-copy">
              <p className="album-title">{playingTrack.album}</p>
              <p className="album-meta">
                {playingTrack.artist}
                {releaseYear ? ` · ${releaseYear}` : ""}
              </p>
            </div>
          </section>
          <section className="current-track" aria-label="当前曲目">
            <p className="track-title">{playingTrack.title}</p>
            {showProgress ? (
              <div className="playback-row">
                <span className="track-time">{formatTime(scrubValue)}</span>
                <input
                  className="seek-bar"
                  type="range"
                  min={0}
                  max={durationMs}
                  value={scrubValue}
                  onChange={(event) =>
                    setScrubPosition(Number(event.target.value))
                  }
                  onPointerUp={commitSeek}
                  onKeyUp={commitSeek}
                  aria-label="播放进度"
                />
                <span className="track-time">{formatTime(durationMs)}</span>
              </div>
            ) : null}
            <div className="transport">
              <button
                className="transport-button"
                type="button"
                aria-label="上一首"
                onClick={() => void window.linerfy.previous()}
              >
                <SkipBack aria-hidden="true" />
              </button>
              <button
                className="transport-button primary"
                type="button"
                aria-label={playingTrack.state === "playing" ? "暂停" : "播放"}
                onClick={() => void window.linerfy.togglePlayback()}
              >
                {playingTrack.state === "playing" ? (
                  <Pause aria-hidden="true" />
                ) : (
                  <Play aria-hidden="true" />
                )}
              </button>
              <button
                className="transport-button"
                type="button"
                aria-label="下一首"
                onClick={() => void window.linerfy.next()}
              >
                <SkipForward aria-hidden="true" />
              </button>
            </div>
          </section>
        </>
      ) : null}

      {auth.status === "signed-in" &&
      (context.status === "ready" || context.status === "partial") ? (
        <div className="context">
          <MusicContextCard
            context={context.context}
            showReleaseHeader={false}
          />
          {context.status === "partial" ? (
            <p className="context-progress" aria-live="polite">
              正在补齐乐评…
            </p>
          ) : null}
        </div>
      ) : contextLabel ? (
        <p
          className={`context-status ${context.status === "error" ? "error" : "muted"}`}
          aria-live="polite"
        >
          {contextLabel}
        </p>
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
