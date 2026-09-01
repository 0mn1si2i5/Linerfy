import { describe, expect, it } from "vitest";

import { createWindowOptions } from "./security";

describe("desktop renderer boundary", () => {
  it("isolates the renderer from Node and the main process", () => {
    const options = createWindowOptions("/fixed/preload.js");

    expect(options.webPreferences).toMatchObject({
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    });
    expect(options.webPreferences?.preload).toBe("/fixed/preload.js");
  });
});
