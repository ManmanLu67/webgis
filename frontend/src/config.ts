export interface LayerSpec {
  id: string
  type: "wmts" | "xyz" | "cog" | "terrain" | "3dtiles"
  url: string
  opacity?: number
  show?: boolean
  maximumScreenSpaceError?: number
  attribution: string
}

export interface ResolvedGlobe {
  ionToken: string
  imagery: LayerSpec
  terrain: LayerSpec
  tileset: LayerSpec
}

const OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

export function resolveGlobeConfig(env: Record<string, string | undefined>): ResolvedGlobe {
  const ionToken = env.VITE_ION_TOKEN?.trim() ?? ""
  const imageryUrl = env.VITE_IMAGERY_URL?.trim() || (ionToken ? "ion://2" : OSM)
  const terrainUrl = env.VITE_TERRAIN_URL?.trim() || (ionToken ? "ion://1" : "ellipsoid://")
  const tilesetUrl = env.VITE_TILESET_URL?.trim() ?? ""
  return {
    ionToken,
    imagery: {
      id: "imagery",
      type: "xyz",
      url: imageryUrl,
      attribution:
        env.VITE_IMAGERY_ATTRIBUTION?.trim() ||
        (imageryUrl.startsWith("ion://") ? "Cesium ion" : "© OpenStreetMap 贡献者"),
    },
    terrain: {
      id: "terrain",
      type: "terrain",
      url: terrainUrl,
      attribution: env.VITE_TERRAIN_ATTRIBUTION?.trim() || "",
    },
    tileset: {
      id: "tileset",
      type: "3dtiles",
      url: tilesetUrl,
      attribution: env.VITE_TILESET_ATTRIBUTION?.trim() || "",
      maximumScreenSpaceError: 16,
    },
  }
}
