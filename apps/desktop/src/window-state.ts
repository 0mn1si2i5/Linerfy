import { promises as fs } from "node:fs";
import path from "node:path";

/** Persisted window geometry. */
export interface WindowState {
  width: number;
  height: number;
  x?: number;
  y?: number;
}

export const MIN_WINDOW_DIMENSION = 200;

export function defaultWindowState(): WindowState {
  return { width: 760, height: 560 };
}

/** Clamp/repair an untrusted persisted value into a valid WindowState. */
export function sanitizeWindowState(value: unknown): WindowState {
  const defaults = defaultWindowState();
  if (typeof value !== "object" || value === null) return defaults;
  const v = value as Record<string, unknown>;
  return {
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
