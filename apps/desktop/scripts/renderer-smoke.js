// Minimal renderer startup smoke. Loads the built renderer bundle in a hidden
// Electron window with the real preload, then asserts that React actually
// mounted content into #root. This catches the duplicate-React black screen
// (two bundled React copies make the first render throw "Cannot read properties
// of null (reading 'useContext')", leaving #root empty) without standing up an
// E2E framework.
//
// Run after `electron-forge package` (which writes .vite/), from apps/desktop:
//   node_modules/.bin/electron scripts/renderer-smoke.js

const { app, BrowserWindow } = require("electron");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const PRELOAD = path.join(ROOT, ".vite", "build", "preload.js");
const RENDERER = path.join(
  ROOT,
  ".vite",
  "renderer",
  "main_window",
  "index.html",
);

const DUP_REACT_RE =
  /useContext|Cannot read properties of null|Minified React error|Invalid hook call/i;

let rendererError = false;
let window = null;

function finish(code, message) {
  console.log(message);
  app.exit(code);
}

app.whenReady().then(() => {
  window = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: PRELOAD,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });

  window.webContents.on("render-process-gone", (_event, details) => {
    rendererError = true;
    console.error("SMOKE: renderer process gone:", details.reason);
  });

  window.webContents.on("console-message", (event) => {
    const message = String(event.message || "");
    const level = event.level ?? event[1];
    // Flag only the errors that indicate a broken React tree. Unhandled IPC
    // rejections are expected here (no main-process handlers are registered in
    // this smoke), so they are deliberately not treated as failures.
    if ((level === "error" || level === 3) && DUP_RE_RE.test(message)) {
      rendererError = true;
      console.error("SMOKE: renderer error:", message);
    }
  });

  window
    .loadFile(RENDERER)
    .then(() => pollContent(0))
    .catch((error) =>
      finish(1, `SMOKE FAIL: could not load renderer: ${error.message}`),
    );
});

function pollContent(attempt) {
  if (rendererError) return finish(1, "SMOKE FAIL: uncaught renderer error");

  window.webContents
    .executeJavaScript(
      `JSON.stringify({
        children: document.getElementById('root')?.children.length || 0,
        text: (document.body?.innerText || '').trim()
      })`,
    )
    .then((raw) => {
      const { children, text } = JSON.parse(raw);
      if (children > 0 && text.length > 0) {
        return finish(
          0,
          `SMOKE PASS: renderer mounted ${children} root child(ren), "${text.slice(0, 60)}..."`,
        );
      }
      if (attempt >= 30) {
        return finish(
          1,
          `SMOKE FAIL: #root stayed empty after ${attempt + 1} polls`,
        );
      }
      setTimeout(() => pollContent(attempt + 1), 100);
    })
    .catch((error) =>
      finish(1, `SMOKE FAIL: evaluate error: ${error.message}`),
    );
}
