import { execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import { MakerZIP } from "@electron-forge/maker-zip";
import { VitePlugin } from "@electron-forge/plugin-vite";
import type { ForgeConfig } from "@electron-forge/shared-types";

const execFileAsync = promisify(execFile);

const config: ForgeConfig = {
  packagerConfig: {
    appBundleId: "app.linerfy.desktop",
    asar: true,
    icon: "assets/app-icon.icns",
    executableName: "Linerfy",
    extendInfo: {
      NSAppleEventsUsageDescription:
        "Linerfy 需要读取 Spotify 或音乐 App 当前播放的曲目，以显示相关乐评。",
    },
  },
  rebuildConfig: {},
  hooks: {
    postPackage: async (_forgeConfig, { platform, outputPaths }) => {
      if (platform !== "darwin") return;
      for (const outputPath of outputPaths) {
        const appPath = path.join(outputPath, "Linerfy.app");
        const temporaryDirectory = await fs.mkdtemp(
          path.join(os.tmpdir(), "linerfy-sign-"),
        );
        const temporaryAppPath = path.join(temporaryDirectory, "Linerfy.app");
        try {
          // Electron's linker signatures do not share an identity. Sign away
          // from synced folders, which can attach metadata rejected by codesign.
          await execFileAsync("ditto", [appPath, temporaryAppPath]);
          await execFileAsync("xattr", ["-cr", temporaryAppPath]);
          await execFileAsync("codesign", [
            "--force",
            "--deep",
            "--sign",
            "-",
            temporaryAppPath,
          ]);
          await execFileAsync("ditto", [temporaryAppPath, appPath]);
        } finally {
          await fs.rm(temporaryDirectory, { recursive: true, force: true });
        }
      }
    },
  },
  makers: [new MakerZIP({}, ["darwin"])],
  plugins: [
    new VitePlugin({
      build: [
        { entry: "src/main.ts", config: "vite.main.config.ts", target: "main" },
        {
          entry: "src/preload.ts",
          config: "vite.preload.config.ts",
          target: "preload",
        },
      ],
      renderer: [{ name: "main_window", config: "vite.renderer.config.ts" }],
    }),
  ],
};

export default config;
