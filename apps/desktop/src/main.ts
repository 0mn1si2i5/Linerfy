import { execFile } from "node:child_process";
import { promisify } from "node:util";

import {
  APPLE_MUSIC_NOW_PLAYING_SCRIPT,
  SPOTIFY_NOW_PLAYING_SCRIPT,
  createAppleMusicProvider,
  createNowPlayingService,
  createSpotifyProvider,
  type ScriptRunner,
} from "@linerfy/now-playing";
import { app, BrowserWindow, ipcMain, shell } from "electron";

import { createWindowOptions } from "./security";

declare const MAIN_WINDOW_VITE_DEV_SERVER_URL: string | undefined;
declare const MAIN_WINDOW_VITE_NAME: string;

const execFileAsync = promisify(execFile);
const allowedScripts = new Set([
  SPOTIFY_NOW_PLAYING_SCRIPT,
  APPLE_MUSIC_NOW_PLAYING_SCRIPT,
]);

const runFixedJxa: ScriptRunner = async (script) => {
  if (!allowedScripts.has(script))
    throw new Error("Only bundled automation programs may run");
  const { stdout } = await execFileAsync("/usr/bin/osascript", [
    "-l",
    "JavaScript",
    "-e",
    script,
  ]);
  return stdout;
};

const nowPlaying = createNowPlayingService([
  createSpotifyProvider(runFixedJxa),
  createAppleMusicProvider(runFixedJxa),
]);

function createWindow() {
  const preload = new URL("preload.js", import.meta.url).pathname;
  const window = new BrowserWindow(createWindowOptions(preload));

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) void shell.openExternal(url);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event) => event.preventDefault());

  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) {
    void window.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    void window.loadFile(
      new URL(
        `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`,
        import.meta.url,
      ).pathname,
    );
  }
}

ipcMain.handle("now-playing:get", async () => {
  if (process.platform !== "darwin") return null;
  return nowPlaying.getNowPlaying();
});

void app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
