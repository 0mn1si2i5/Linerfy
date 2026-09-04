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
  alwaysOnTop?: boolean;
  skipTaskbar?: boolean;
  show?: boolean;
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
    minWidth: 360,
    minHeight: 560,
    backgroundColor: "#121212",
    title: "Linerfy",
    frame: true,
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 14, y: 20 },
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
