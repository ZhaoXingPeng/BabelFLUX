import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  publicDir: fileURLToPath(new URL("../frontend/public", import.meta.url)),
  resolve: {
    alias: {
      "@frontend": fileURLToPath(new URL("../frontend/src", import.meta.url))
    }
  },
  server: {
    host: "0.0.0.0",
    port: 5175,
    fs: {
      allow: [".."]
    }
  },
  build: {
    target: "es2022"
  }
});
