import * as Cesium from "cesium"
import {
  clampOpacity,
  registerLayerType,
  type LayerHandle,
  type LayerSpec,
} from "./layerTypeRegistry"

let token = ""

export function configureCesium(options: { token: string }): void {
  token = options.token
  if (token) {
    Cesium.Ion.defaultAccessToken = token
  }
}

function assetId(url: string): number {
  const id = Number(url.slice("ion://".length))
  if (!Number.isFinite(id) || id <= 0) {
    throw new Error(`无法解析资产地址: ${url}`)
  }
  return id
}

function imageryProvider(spec: LayerSpec): Promise<Cesium.ImageryProvider> | Cesium.ImageryProvider {
  if (spec.crs === "GCJ-02") {
    throw new Error("GCJ-02 不能直接叠到 WGS84 地球上")
  }
  if (spec.url.startsWith("ion://")) {
    if (!token) throw new Error("使用 ion 影像前需要配置访问令牌")
    return Cesium.IonImageryProvider.fromAssetId(assetId(spec.url))
  }
  const scheme =
    spec.tilingScheme === "Geographic"
      ? new Cesium.GeographicTilingScheme()
      : new Cesium.WebMercatorTilingScheme()
  return new Cesium.UrlTemplateImageryProvider({
    url: spec.url,
    credit: spec.attribution,
    tilingScheme: scheme,
    maximumLevel: spec.maxZoom,
  })
}

registerLayerType("xyz", (spec) => imageryController(spec))
registerLayerType("cog", (spec) => imageryController(spec))
registerLayerType("wmts", (spec) => imageryController(spec))

registerLayerType("terrain", (spec) => ({
  attribution: spec.attribution ?? "",
  async attach(viewer) {
    const globe = viewer as Cesium.Viewer
    const provider = await terrainProvider(spec)
    globe.terrainProvider = provider
    let active: Cesium.TerrainProvider = provider
    return {
      attribution: spec.attribution ?? "",
      setShow(show: boolean) {
        if (show) {
          globe.terrainProvider = active
        } else {
          globe.terrainProvider = new Cesium.EllipsoidTerrainProvider()
        }
      },
      setOpacity() {},
      setMaximumScreenSpaceError() {},
      setSplit() {},
      remove() {},
    } satisfies LayerHandle
  },
}))

registerLayerType("3dtiles", (spec) => ({
  attribution: spec.attribution ?? "",
  async attach(viewer) {
    const globe = viewer as Cesium.Viewer
    if (!spec.url) {
      throw new Error("未配置三维瓦片地址")
    }
    const tileset = await Cesium.Cesium3DTileset.fromUrl(spec.url)
    tileset.maximumScreenSpaceError = spec.maximumScreenSpaceError ?? 16
    globe.scene.primitives.add(tileset)
    return {
      attribution: spec.attribution ?? "",
      setShow(show: boolean) {
        tileset.show = show
      },
      setOpacity() {},
      setMaximumScreenSpaceError(value: number) {
        tileset.maximumScreenSpaceError = value
      },
      setSplit() {},
      remove() {
        globe.scene.primitives.remove(tileset)
      },
    } satisfies LayerHandle
  },
}))

function imageryController(spec: LayerSpec) {
  return {
    attribution: spec.attribution ?? "",
    async attach(viewer: unknown): Promise<LayerHandle> {
      const globe = viewer as Cesium.Viewer
      const provider = await imageryProvider(spec)
      const layer = globe.imageryLayers.addImageryProvider(provider)
      layer.alpha = clampOpacity(spec.opacity ?? 1)
      layer.show = spec.show !== false
      return {
        attribution: spec.attribution ?? "",
        setShow(show: boolean) {
          layer.show = show
        },
        setOpacity(opacity: number) {
          layer.alpha = clampOpacity(opacity)
        },
        setMaximumScreenSpaceError() {},
        setSplit(side) {
          layer.splitDirection =
            side === "left"
              ? Cesium.SplitDirection.LEFT
              : side === "right"
                ? Cesium.SplitDirection.RIGHT
                : Cesium.SplitDirection.NONE
        },
        remove() {
          globe.imageryLayers.remove(layer, true)
        },
      }
    },
  }
}

async function terrainProvider(spec: LayerSpec): Promise<Cesium.TerrainProvider> {
  if (!spec.url || spec.url === "ellipsoid://") {
    return new Cesium.EllipsoidTerrainProvider()
  }
  if (spec.url.startsWith("ion://")) {
    if (!token) throw new Error("使用 ion 地形前需要配置访问令牌")
    return Cesium.CesiumTerrainProvider.fromIonAssetId(assetId(spec.url))
  }
  return Cesium.CesiumTerrainProvider.fromUrl(spec.url)
}
