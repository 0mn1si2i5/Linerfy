import { execFile } from "node:child_process";
import { promisify } from "node:util";

import {
  APPLE_MUSIC_NOW_PLAYING_SCRIPT,
  SPOTIFY_NOW_PLAYING_SCRIPT,
  createAppleMusicProvider,
  createNowPlayingService,
  createSpotifyProvider,
  type NowPlayingTrack,
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
import {
  trackKey,
  type ContextApiResponse,
  type ContextState,
} from "./context-state";
import {
  performOAuthFlow,
  refreshSession,
  type SupabaseSession,
} from "./oauth";
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

function isSessionExpired(session: SupabaseSession): boolean {
  return Boolean(session.expires_at && session.expires_at * 1000 <= Date.now());
}

function loginState(): LoginState {
  const session = loadSession();
  return session && !isSessionExpired(session)
    ? { status: "signed-in" }
    : { status: "signed-out" };
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

// Refresh the persisted session with its refresh token, or clear it and sign
// out if the refresh fails (revoked/expired refresh token). Returns the fresh
// session, or null when there is nothing usable left.
async function refreshOrClear(): Promise<SupabaseSession | null> {
  const session = loadSession();
  if (!session) return null;
  const config = oauthConfig();
  if (!config) {
    tokenStore?.clear();
    sendAuthState();
    return null;
  }
  try {
    const refreshed = await refreshSession(config, session.refresh_token);
    tokenStore?.save(JSON.stringify(refreshed));
    return refreshed;
  } catch {
    tokenStore?.clear();
    sendAuthState();
    return null;
  }
}

// Return a non-expired session, refreshing it first when it is within 60s of
// expiry (or already past it). Never returns an expired token to a caller.
async function ensureFreshSession(): Promise<SupabaseSession | null> {
  const session = loadSession();
  if (!session) return null;
  if (session.expires_at && session.expires_at * 1000 > Date.now() + 60_000) {
    return session;
  }
  return refreshOrClear();
}

// The authenticated API base (e.g. the Vercel deployment). Context fetching is
// disabled until it and a session are both present.
const apiUrl = process.env.LINERFY_API_URL;

let contextFetchSeq = 0;
let lastFetchedTrackKey: string | null = null;
let pendingContext = false;

function sendContext(state: ContextState) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("context:changed", state);
  }
}

// Fetch context for the current track, discarding stale responses: the seq
// guard ensures only the latest request is rendered, and `lastFetchedTrackKey`
// avoids re-fetching an already-ready track on every poll.
async function fetchContextForTrack(track: NowPlayingTrack) {
  if (!apiUrl) {
    sendContext({ status: "idle" });
    return;
  }
  let session = await ensureFreshSession();
  if (!session) {
    sendContext({ status: "idle" });
    return;
  }
  const seq = ++contextFetchSeq;
  sendContext({ status: "loading" });

  const post = (token: string) =>
    fetch(`${apiUrl.replace(/\/+$/, "")}/api/context`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        provider: track.provider,
        title: track.title,
        artist: track.artist,
        album: track.album,
        state: track.state,
        ...(track.providerUrl ? { providerUrl: track.providerUrl } : {}),
      }),
    });

  let response: Response;
  try {
    response = await post(session.access_token);
  } catch {
    if (seq === contextFetchSeq) {
      pendingContext = true;
      sendContext({ status: "error", message: "网络错误" });
    }
    return;
  }
  if (seq !== contextFetchSeq) return;

  // A 401/403 means the access token is stale or revoked: refresh once and
  // retry. If the refresh (or the retry) still fails, clear the session so the
  // UI falls back to signed-out rather than showing a stale logged-in state.
  if (response.status === 401 || response.status === 403) {
    session = await refreshOrClear();
    if (!session) {
      if (seq === contextFetchSeq) sendContext({ status: "idle" });
      return;
    }
    try {
      response = await post(session.access_token);
    } catch {
      if (seq === contextFetchSeq) {
        pendingContext = true;
        sendContext({ status: "error", message: "网络错误" });
      }
      return;
    }
    if (seq !== contextFetchSeq) return;
    if (response.status === 401 || response.status === 403) {
      tokenStore?.clear();
      sendAuthState();
      if (seq === contextFetchSeq) sendContext({ status: "idle" });
      return;
    }
  }

  let body: ContextApiResponse;
  try {
    body = (await response.json()) as ContextApiResponse;
  } catch {
    if (seq === contextFetchSeq) {
      pendingContext = true;
      sendContext({ status: "error", message: "网络错误" });
    }
    return;
  }
  if (seq !== contextFetchSeq) return;
  lastFetchedTrackKey = trackKey(track);
  if (body.status === "ready") {
    pendingContext = false;
    sendContext({ status: "ready", context: body.context });
  } else if (body.status === "queued" || body.status === "running") {
    pendingContext = true;
    sendContext({ status: body.status, stage: body.stage ?? "" });
  } else {
    pendingContext = false;
    sendContext({ status: body.status });
  }
}

function maybeFetchContext(track: NowPlayingTrack | null) {
  if (!track) {
    lastFetchedTrackKey = null;
    pendingContext = false;
    sendContext({ status: "idle" });
    return;
  }
  const key = trackKey(track);
  if (key === lastFetchedTrackKey && !pendingContext) return;
  void fetchContextForTrack(track);
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
    maybeFetchContext(track);
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
  lastFetchedTrackKey = null;
  pendingContext = false;
  sendContext({ status: "idle" });
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
    lastFetchedTrackKey = null;
    pendingContext = false;
    void nowPlaying.getNowPlaying().then(maybeFetchContext);
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
