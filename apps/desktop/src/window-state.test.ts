import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  defaultWindowState,
  loadWindowState,
  sanitizeWindowState,
  saveWindowState,
} from "./window-state";

async function tempFile(): Promise<string> {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "linerfy-state-"));
  return path.join(dir, "window-state.json");
}

describe("window state", () => {
  it("defaults to a locked window", () => {
    expect(defaultWindowState().locked).toBe(true);
  });

  it("repairs a malformed persisted state to safe defaults", () => {
    expect(
      sanitizeWindowState({ locked: false, width: 1, height: 10 }),
    ).toEqual({ locked: false, width: 760, height: 560 });
    expect(sanitizeWindowState("garbage")).toEqual(defaultWindowState());
    expect(sanitizeWindowState(null)).toEqual(defaultWindowState());
  });

  it("keeps valid fields including optional position", () => {
    expect(
      sanitizeWindowState({
        locked: false,
        width: 900,
        height: 700,
        x: 12,
        y: 34,
      }),
    ).toEqual({ locked: false, width: 900, height: 700, x: 12, y: 34 });
  });

  it("round-trips state through a file", async () => {
    const file = await tempFile();
    await saveWindowState(file, {
      locked: false,
      width: 800,
      height: 600,
      x: 5,
      y: 6,
    });
    await expect(loadWindowState(file)).resolves.toEqual({
      locked: false,
      width: 800,
      height: 600,
      x: 5,
      y: 6,
    });
  });

  it("falls back to defaults when the file is absent or corrupt", async () => {
    const file = await tempFile();
    await expect(loadWindowState(file)).resolves.toEqual(defaultWindowState());

    await fs.writeFile(file, "{ not json", "utf-8");
    await expect(loadWindowState(file)).resolves.toEqual(defaultWindowState());
  });
});
