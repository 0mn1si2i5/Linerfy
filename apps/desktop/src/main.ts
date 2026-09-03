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
import {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  nativeImage,
  safeStorage,
  screen,
  shell,
  Tray,
} from "electron";

import type { LoginState, SignInResult } from "./auth-state";
import { performOAuthFlow, type SupabaseSession } from "./oauth";
import { createWindowOptions } from "./security";
import {
  createTokenStore,
  type SafeCrypto,
  type TokenStore,
} from "./token-store";
import { TRAY_ICON_DATA_URL } from "./tray-icon";
import {
  defaultWindowState,
  loadWindowState,
  popoverHeight,
  saveWindowState,
  POPOVER_WIDTH,
  type WindowState,
} from "./window-state";

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

const POLL_INTERVAL_MS = 2500;
const TOGGLE_SHORTCUT = "CommandOrControl+Shift+L";

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let state: WindowState = defaultWindowState();
let isQuitting = false;
let pollTimer: NodeJS.Timeout | null = null;

const stateFile = () => `${app.getPath("userData")}/window-state.json`;
const tokenFile = () => `${app.getPath("userData")}/session-token.json`;

// Encrypt the session token with the OS secure storage (Keychain on macOS).
const safeCrypto: SafeCrypto = {
  isAvailable: () => safeStorage.isEncryptionAvailable(),
  encrypt: (plain) => safeStorage.encryptString(plain).toString("base64"),
  decrypt: (cipher) => safeStorage.decryptString(Buffer.from(cipher, "base64")),
};

let tokenStore: TokenStore | null = null;

// The session is persisted as a single encrypted blob: a JSON string of the
// access/refresh tokens. `load()` decrypts it; this parses it back.
function loadSession(): SupabaseSession | null {
  const raw = tokenStore?.load();
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as SupabaseSession;
    return parsed.access_token && parsed.refresh_token ? parsed : null;
  } catch {
    return null;
  }
}

function loginState(): LoginState {
  return loadSession() ? { status: "signed-in" } : { status: "signed-out" };
}

function oauthConfig() {
  const url = process.env.SUPABASE_URL;
  const anonKey = process.env.SUPABASE_PUBLISHABLE_KEY;
  if (!url || !anonKey) return null;
  const redirectPort = Number(
    process.env.LINERFY_OAUTH_REDIRECT_PORT ?? "4862",
  );
  return {
    url,
    anonKey,
    provider: "github" as const,
    redirectPort: Number.isFinite(redirectPort) ? redirectPort : 4862,
  };
}

function sendAuthState() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("auth:state", loginState());
  }
}

function popoverSize(): { width: number; height: number } {
  return {
    width: POPOVER_WIDTH,
    height: popoverHeight(screen.getPrimaryDisplay().workArea.height),
  };
}

function windowStyle() {
  if (state.locked) {
    return {
      ...popoverSize(),
      resizable: false,
      movable: false,
      alwaysOnTop: true,
      skipTaskbar: true,
    };
  }
  return {
    width: state.width,
    height: state.height,
    ...(state.x !== undefined ? { x: state.x } : {}),
    ...(state.y !== undefined ? { y: state.y } : {}),
    resizable: true,
    movable: true,
    alwaysOnTop: false,
    skipTaskbar: false,
  };
}

function positionPopover(window: BrowserWindow) {
  if (!state.locked || !tray) return;
  const trayBounds = tray.getBounds();
  const { width, height } = popoverSize();
  const x = Math.round(trayBounds.x + trayBounds.width / 2 - width / 2);
  const y = Math.round(trayBounds.y + trayBounds.height + 4);
  window.setBounds({ x, y, width, height });
}

function loadRenderer(window: BrowserWindow) {
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

function captureNormalBounds(window: BrowserWindow) {
  if (state.locked) return;
  const bounds = window.getBounds();
  state = {
    ...state,
    width: bounds.width,
    height: bounds.height,
    x: bounds.x,
    y: bounds.y,
  };
}

function sendNowPlaying() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  void nowPlaying.getNowPlaying().then((track) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("now-playing:changed", track);
    }
  });
}

function startPolling() {
  if (pollTimer) return;
  sendNowPlaying();
  pollTimer = setInterval(sendNowPlaying, POLL_INTERVAL_MS);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function applyMode(window: BrowserWindow) {
  captureNormalBounds(window);
  if (state.locked) {
    window.setResizable(false);
    window.setMovable(false);
    window.setAlwaysOnTop(true);
    window.setSkipTaskbar(true);
    positionPopover(window);
  } else {
    window.setAlwaysOnTop(false);
    window.setSkipTaskbar(false);
    window.setMovable(true);
    window.setResizable(true);
    window.setBounds({
      x: state.x ?? 0,
      y: state.y ?? 0,
      width: state.width,
      height: state.height,
    });
  }
  await saveWindowState(stateFile(), state);
  window.webContents.send("window:state", { locked: state.locked });
}

function toggleWindow() {
  if (!mainWindow) return;
  if (mainWindow.isVisible()) {
    mainWindow.hide();
    stopPolling();
  } else {
    positionPopover(mainWindow);
    mainWindow.show();
    mainWindow.focus();
    startPolling();
  }
}

function createWindow() {
  const preload = new URL("preload.js", import.meta.url).pathname;
  const window = new BrowserWindow(
    createWindowOptions(preload, { ...windowStyle(), frame: false }),
  );

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) void shell.openExternal(url);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event) => event.preventDefault());

  window.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      captureNormalBounds(window);
      void saveWindowState(stateFile(), state);
      stopPolling();
      window.hide();
    }
  });
  window.on("moved", () => captureNormalBounds(window));
  window.on("resized", () => captureNormalBounds(window));

  loadRenderer(window);
  mainWindow = window;
}

function createTray() {
  const icon = nativeImage.createFromDataURL(TRAY_ICON_DATA_URL);
  icon.setTemplateImage(true);
  tray = new Tray(icon);
  tray.setToolTip("Linerfy");
  tray.on("click", () => toggleWindow());
}

ipcMain.handle("now-playing:get", async () => {
  if (process.platform !== "darwin") return null;
  return nowPlaying.getNowPlaying();
});

ipcMain.handle("window:get-state", () => ({ locked: state.locked }));

ipcMain.handle("window:set-locked", async (_event, locked: boolean) => {
  state = { ...state, locked };
  if (mainWindow) await applyMode(mainWindow);
});

ipcMain.handle("auth:get-state", () => loginState());

ipcMain.handle("auth:sign-out", () => {
  tokenStore?.clear();
  sendAuthState();
});

ipcMain.handle("auth:sign-in", async (): Promise<SignInResult> => {
  const config = oauthConfig();
  if (!config) {
    return {
      status: "error",
      message: "OAuth 未配置：缺少 SUPABASE_URL 或 SUPABASE_PUBLISHABLE_KEY",
    };
  }
  try {
    const session = await performOAuthFlow(config, (url) =>
      shell.openExternal(url),
    );
    tokenStore?.save(JSON.stringify(session));
    sendAuthState();
    return loginState();
  } catch (error) {
    return {
      status: "error",
      message: error instanceof Error ? error.message : String(error),
    };
  }
});

void app.whenReady().then(async () => {
  state = await loadWindowState(stateFile());
  tokenStore = createTokenStore(tokenFile(), safeCrypto);
  createWindow();
  createTray();
  globalShortcut.register(TOGGLE_SHORTCUT, () => toggleWindow());
  app.on("activate", () => {
    if (mainWindow && !mainWindow.isVisible()) toggleWindow();
  });
});

app.on("before-quit", () => {
  isQuitting = true;
  stopPolling();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
