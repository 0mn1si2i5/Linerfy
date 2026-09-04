import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Force a single React/ReactDOM copy into the renderer bundle. The pnpm
    // hoist layout can otherwise resolve `react` from two different physical
    // locations (the workspace symlink into .pnpm and a separately-hoisted root
    // copy), which bundles React twice and breaks hooks with
    // "Cannot read properties of null (reading 'useContext')".
    dedupe: ["react", "react-dom"],
  },
});
