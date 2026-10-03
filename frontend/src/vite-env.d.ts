interface ImportMetaEnv {
  readonly VITE_ION_TOKEN?: string
  readonly VITE_IMAGERY_URL?: string
  readonly VITE_IMAGERY_ATTRIBUTION?: string
  readonly VITE_TERRAIN_URL?: string
  readonly VITE_TERRAIN_ATTRIBUTION?: string
  readonly VITE_TILESET_URL?: string
  readonly VITE_TILESET_ATTRIBUTION?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
