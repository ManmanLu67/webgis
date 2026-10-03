/// <reference types="vite/client" />

// 单文件组件由 vite-plugin-vue 编译，tsc 不认识 .vue 后缀，这里补一个声明。
// 真正做模板内类型检查要上 vue-tsc，那是另一件事。
declare module "*.vue" {
  import type { DefineComponent } from "vue"
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}

interface ImportMetaEnv {
  readonly VITE_ION_TOKEN?: string
  readonly VITE_IMAGERY_URL?: string
  readonly VITE_IMAGERY_ATTRIBUTION?: string
  readonly VITE_TERRAIN_URL?: string
  readonly VITE_TERRAIN_ATTRIBUTION?: string
  readonly VITE_TILESET_URL?: string
  readonly VITE_TILESET_ATTRIBUTION?: string
  /** 开发期 vite 代理指向的后端地址 */
  readonly VITE_API_PROXY_TARGET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}