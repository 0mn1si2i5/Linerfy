import type { NowPlayingTrack } from "@linerfy/now-playing";
import { contextBridge, ipcRenderer } from "electron";

import type { LoginState, SignInResult } from "./auth-state";
import type { ContextState } from "./context-state";

export interface WindowLockState {
  locked: boolean;
}

export interface LinerfyDesktopBridge {
  getNowPlaying(): Promise<NowPlayingTrack | null>;
  onNowPlayingChanged(
    callback: (track: NowPlayingTrack | null) => void,
  ): () => void;
  previous(): Promise<void>;
  togglePlayback(): Promise<void>;
  next(): Promise<void>;
  seekTo(positionMs: number): Promise<void>;
  getWindowState(): Promise<WindowLockState>;
  setWindowLocked(locked: boolean): Promise<void>;
  onWindowStateChanged(callback: (state: WindowLockState) => void): () => void;
  getAuthState(): Promise<LoginState>;
  signIn(): Promise<SignInResult>;
  signOut(): Promise<void>;
  onAuthStateChanged(callback: (state: LoginState) => void): () => void;
  onContextChanged(callback: (state: ContextState) => void): () => void;
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
  previous: () =>
    ipcRenderer.invoke("playback:control", "previous") as Promise<void>,
  togglePlayback: () =>
    ipcRenderer.invoke("playback:control", "toggle") as Promise<void>,
  next: () => ipcRenderer.invoke("playback:control", "next") as Promise<void>,
  seekTo: (positionMs: number) =>
    ipcRenderer.invoke("playback:seek", positionMs) as Promise<void>,
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
  getAuthState: () =>
    ipcRenderer.invoke("auth:get-state") as Promise<LoginState>,
  signIn: () => ipcRenderer.invoke("auth:sign-in") as Promise<SignInResult>,
  signOut: () => ipcRenderer.invoke("auth:sign-out") as Promise<void>,
  onAuthStateChanged: (callback: (state: LoginState) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, state: LoginState) =>
      callback(state);
    ipcRenderer.on("auth:state", listener);
    return () => ipcRenderer.removeListener("auth:state", listener);
  },
  onContextChanged: (callback: (state: ContextState) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, state: ContextState) =>
      callback(state);
    ipcRenderer.on("context:changed", listener);
    return () => ipcRenderer.removeListener("context:changed", listener);
  },
} satisfies LinerfyDesktopBridge);
