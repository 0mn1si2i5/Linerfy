import type { BrowserWindowConstructorOptions } from "electron";

export function createWindowOptions(
  preload: string,
): BrowserWindowConstructorOptions {
  return {
    width: 1080,
    height: 760,
    minWidth: 760,
    minHeight: 560,
    backgroundColor: "#f3efe5",
    title: "Linerfy",
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  };
}
