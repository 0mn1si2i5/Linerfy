import { promises as fs } from "node:fs";
import path from "node:path";

/** Persisted window geometry: the locked flag plus the last normal-window bounds. */
export interface WindowState {
  locked: boolean;
  width: number;
  height: number;
  x?: number;
  y?: number;
}

/** Popover width (px). Height is computed from the screen's work area. */
export const POPOVER_WIDTH = 440;
export const POPOVER_HEIGHT_RATIO = 0.7;
export const MIN_WINDOW_DIMENSION = 200;

export function defaultWindowState(): WindowState {
  return { locked: true, width: 760, height: 560 };
}

/** Clamp/repair an untrusted persisted value into a valid WindowState. */
export function sanitizeWindowState(value: unknown): WindowState {
  const defaults = defaultWindowState();
  if (typeof value !== "object" || value === null) return defaults;
  const v = value as Record<string, unknown>;
  return {
    locked: typeof v.locked === "boolean" ? v.locked : defaults.locked,
    width:
      typeof v.width === "number" && v.width >= MIN_WINDOW_DIMENSION
        ? v.width
        : defaults.width,
    height:
      typeof v.height === "number" && v.height >= MIN_WINDOW_DIMENSION
        ? v.height
        : defaults.height,
    ...(typeof v.x === "number" ? { x: v.x } : {}),
    ...(typeof v.y === "number" ? { y: v.y } : {}),
  };
}

export async function loadWindowState(file: string): Promise<WindowState> {
  try {
    return sanitizeWindowState(JSON.parse(await fs.readFile(file, "utf-8")));
  } catch {
    return defaultWindowState();
  }
}

export async function saveWindowState(
  file: string,
  state: WindowState,
): Promise<void> {
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, JSON.stringify(state, null, 2), "utf-8");
}

/** Height of the popover for a given screen work-area height (70%, rounded). */
export function popoverHeight(workAreaHeight: number): number {
  return Math.max(
    MIN_WINDOW_DIMENSION,
    Math.round(workAreaHeight * POPOVER_HEIGHT_RATIO),
  );
}
