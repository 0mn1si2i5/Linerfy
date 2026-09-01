import type { NowPlayingTrack } from "@linerfy/now-playing";
import { contextBridge, ipcRenderer } from "electron";

export interface LinerfyDesktopBridge {
  getNowPlaying(): Promise<NowPlayingTrack | null>;
}

contextBridge.exposeInMainWorld("linerfy", {
  getNowPlaying: () =>
    ipcRenderer.invoke("now-playing:get") as Promise<NowPlayingTrack | null>,
} satisfies LinerfyDesktopBridge);
