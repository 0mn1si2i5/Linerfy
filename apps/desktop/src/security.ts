import type { BrowserWindowConstructorOptions } from "electron";

/** Non-security window chrome, overridable per mode (popover vs normal). */
export interface WindowStyleOptions {
  width?: number;
  height?: number;
  minWidth?: number;
  minHeight?: number;
  x?: number;
  y?: number;
  resizable?: boolean;
  movable?: boolean;
  frame?: boolean;
  alwaysOnTop?: boolean;
  skipTaskbar?: boolean;
}

/**
 * Build the window options with the renderer security boundary fixed and only
 * the chrome adjustable. The security fields are non-negotiable regardless of
 * popover/normal mode.
 */
export function createWindowOptions(
  preload: string,
  style: WindowStyleOptions = {},
): BrowserWindowConstructorOptions {
  return {
    width: 1080,
    height: 760,
    minWidth: 760,
    minHeight: 560,
    backgroundColor: "#f3efe5",
    title: "Linerfy",
    ...style,
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  };
}
