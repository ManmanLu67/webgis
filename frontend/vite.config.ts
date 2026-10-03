import vue from "@vitejs/plugin-vue"
import cesium from "vite-plugin-cesium"
import { defineConfig } from "vitest/config"

// 开发期把 /api 打到本地后端。生产路径不走这里：compose 里的 gateway
// 自己做前缀转换（/api 剥掉、/cog 原样透传），所以 vite 的 proxy 只在
// `pnpm dev` 时有意义，`pnpm preview` 也不读它。
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000"

export default defineConfig({
  plugins: [vue(), cesium()],
  server: {
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      // 切片路由不带 /api 前缀，别漏掉，否则开发期入库图层拉不到瓦片。
      "/cog": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
})