import type { NowPlayingTrack } from "@linerfy/now-playing";
import { contextBridge, ipcRenderer } from "electron";

export interface WindowLockState {
  locked: boolean;
}

export interface LinerfyDesktopBridge {
  getNowPlaying(): Promise<NowPlayingTrack | null>;
  onNowPlayingChanged(
    callback: (track: NowPlayingTrack | null) => void,
  ): () => void;
  getWindowState(): Promise<WindowLockState>;
  setWindowLocked(locked: boolean): Promise<void>;
  onWindowStateChanged(callback: (state: WindowLockState) => void): () => void;
}

contextBridge.exposeInMainWorld("linerfy", {
  getNowPlaying: () =>
    ipcRenderer.invoke("now-playing:get") as Promise<NowPlayingTrack | null>,
  onNowPlayingChanged: (callback: (track: NowPlayingTrack | null) => void) => {
    const listener = (
      _event: Electron.IpcRendererEvent,
      track: NowPlayingTrack | null,
    ) => callback(track);
    ipcRenderer.on("now-playing:changed", listener);
    return () => ipcRenderer.removeListener("now-playing:changed", listener);
  },
  getWindowState: () =>
    ipcRenderer.invoke("window:get-state") as Promise<WindowLockState>,
  setWindowLocked: (locked: boolean) =>
    ipcRenderer.invoke("window:set-locked", locked) as Promise<void>,
  onWindowStateChanged: (callback: (state: WindowLockState) => void) => {
    const listener = (
      _event: Electron.IpcRendererEvent,
      state: WindowLockState,
    ) => callback(state);
    ipcRenderer.on("window:state", listener);
    return () => ipcRenderer.removeListener("window:state", listener);
  },
} satisfies LinerfyDesktopBridge);
