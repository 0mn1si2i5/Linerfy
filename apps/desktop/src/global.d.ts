import type { LinerfyDesktopBridge } from "./preload";

declare global {
  interface Window {
    linerfy: LinerfyDesktopBridge;
  }
}

export {};
