import { featuredContext } from "@linerfy/domain/fixtures";
import { LinerfyMark, MusicContextCard } from "@linerfy/ui";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";

import "./renderer.css";

function DesktopApp() {
  const [status, setStatus] = useState("读取 Spotify 或 Apple Music 当前播放");

  const refresh = async () => {
    setStatus("正在读取…");
    const track = await window.linerfy.getNowPlaying();
    setStatus(
      track ? `${track.title} — ${track.artist}` : "没有检测到正在播放的音乐",
    );
  };

  return (
    <main>
      <header className="desktop-header">
        <span className="brand">
          <LinerfyMark /> Linerfy
        </span>
        <button type="button" onClick={() => void refresh()}>
          读取当前播放
        </button>
      </header>
      <p className="now-playing" aria-live="polite">
        {status}
      </p>
      <MusicContextCard context={featuredContext} />
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
