import { useEffect, useRef, useState } from "react";

import type { NowPlayingTrack } from "@linerfy/now-playing";

import type { LyricsResult } from "./lyrics";

function activeLineIndex(
  lines: Array<{ timeMs: number }>,
  positionMs: number,
): number {
  let index = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i]!.timeMs <= positionMs) index = i;
    else break;
  }
  return index;
}

function LyricsSource({ url }: { url: string }) {
  return (
    <a className="lyrics-source" href={url} rel="noreferrer" target="_blank">
      歌词来源：LRCLIB
      <span aria-hidden="true">↗</span>
    </a>
  );
}

/**
 * Collapsible lyrics content. The renderer opens this only on demand; the
 * fetch itself lives in the main process. Synced lines highlight the current
 * line from the player's position with a small local interpolation (no
 * per-line network or AppleScript), pause freezes, and seek re-anchors. Manual
 * scrolling pauses auto-follow until the track changes.
 */
export function LyricsPanel({
  track,
  result,
  loading,
}: {
  track: NowPlayingTrack | null;
  result: LyricsResult | null;
  loading: boolean;
}) {
  const activeRef = useRef<HTMLParagraphElement | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [nowMs, setNowMs] = useState(0);
  const anchorRef = useRef({ position: 0, at: 0 });

  // Re-anchor on each fresh player position (poll or seek).
  useEffect(() => {
    if (track?.positionMs !== undefined) {
      anchorRef.current = { position: track.positionMs, at: performance.now() };
      setNowMs(track.positionMs);
    }
  }, [track?.positionMs]);

  // Advance a local clock while playing; freeze when paused.
  useEffect(() => {
    const id = window.setInterval(() => {
      const anchor = anchorRef.current;
      const position =
        track?.state === "playing"
          ? anchor.position + (performance.now() - anchor.at)
          : anchor.position;
      setNowMs(position);
    }, 250);
    return () => window.clearInterval(id);
  }, [track?.state]);

  // Resume auto-follow when a different track's lyrics load.
  const resultKey = result !== null ? result.trackKey : null;
  useEffect(() => {
    setAutoScroll(true);
  }, [resultKey]);

  if (loading) {
    return <p className="lyrics-note muted">正在查找歌词…</p>;
  }
  if (result === null) return null;

  if (result.status === "error") {
    return <p className="lyrics-note error">{result.message}</p>;
  }
  if (result.status === "unavailable") {
    return <p className="lyrics-note muted">未找到这首歌的歌词</p>;
  }
  if (result.status === "instrumental") {
    return <p className="lyrics-note muted">纯音乐，无歌词</p>;
  }

  if (result.status === "plain") {
    return (
      <div className="lyrics-panel">
        <div className="lyrics-plain">{result.text}</div>
        <LyricsSource url={result.sourceUrl} />
      </div>
    );
  }

  const activeIndex = activeLineIndex(result.lines, nowMs);
  useEffect(() => {
    if (!autoScroll) return;
    activeRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeIndex, autoScroll]);

  return (
    <div
      className="lyrics-panel"
      onWheel={() => setAutoScroll(false)}
      onTouchMove={() => setAutoScroll(false)}
    >
      <div className="lyrics-synced">
        {result.lines.map((line, index) => (
          <p
            key={`${line.timeMs}-${index}`}
            ref={index === activeIndex ? activeRef : undefined}
            className={
              index === activeIndex ? "lyrics-line active" : "lyrics-line"
            }
          >
            {line.text}
          </p>
        ))}
      </div>
      <LyricsSource url={result.sourceUrl} />
    </div>
  );
}
