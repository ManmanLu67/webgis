import vue from "@vitejs/plugin-vue"
import cesium from "vite-plugin-cesium"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [vue(), cesium()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
})
