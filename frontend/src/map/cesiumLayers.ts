import * as Cesium from "cesium"
import { checkGeoreference } from "./georeference"
import { tileGridOf } from "./tileGrid"
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

/** 挂载前先过一遍坐标与网格，失败要给出能照着改的中文原因。 */
function assertMountable(spec: LayerSpec): void {
  const verdict = checkGeoreference(spec)
  if (!verdict.ok) {
    throw new Error(verdict.reason ?? "该图层无法直接叠到地球上")
  }
}

function tilingSchemeOf(spec: LayerSpec): Cesium.TilingScheme {
  if (spec.tilingScheme !== "Geographic") return new Cesium.WebMercatorTilingScheme()
  const grid = tileGridOf(spec)
  // 默认 2×1 不传参，避免和 Cesium 自己的零级定义分叉。
  if (grid.levelZeroTilesX === 2 && grid.levelZeroTilesY === 1) {
    return new Cesium.GeographicTilingScheme()
  }
  return new Cesium.GeographicTilingScheme({
    numberOfLevelZeroTilesX: grid.levelZeroTilesX,
    numberOfLevelZeroTilesY: grid.levelZeroTilesY,
  })
}

function xyzProvider(spec: LayerSpec): Cesium.ImageryProvider {
  assertMountable(spec)
  const grid = tileGridOf(spec)
  const options: ConstructorParameters<typeof Cesium.UrlTemplateImageryProvider>[0] = {
    url: spec.url,
    credit: spec.attribution,
    tilingScheme: tilingSchemeOf(spec),
    maximumLevel: spec.maxZoom,
  }
  if (grid.tilePixelSize !== 256) {
    options.tileWidth = grid.tilePixelSize
    options.tileHeight = grid.tilePixelSize
  }
  // 服务方的级别比 Cesium 的高一截时，不能用 `{z}`：那会被填成 Cesium 级别。
  if (grid.customLevel) {
    const offset = grid.levelOffset
    options.customTags = {
      gibsLevel(_provider: Cesium.ImageryProvider, _x: number, _y: number, level: number): string {
        return String(level + offset)
      },
    }
  }
  return new Cesium.UrlTemplateImageryProvider(options)
}

/**
 * 真 WMTS。OGC 定义了两种编码，Cesium 靠地址里有没有 `{}` 占位符自动判别：
 * 有就走 RESTful（直接填模板），没有就走 KVP（把 SERVICE/VERSION/REQUEST 与
 * 图层、格网补成查询参数，VERSION 固定 1.0.0）。两种都要支持，否则
 * 天地图这类 KVP 服务要么接不上，要么得靠"拿 XYZ 模板冒充 WMTS"。
 */
function wmtsProvider(spec: LayerSpec): Cesium.ImageryProvider {
  assertMountable(spec)
  if (!spec.wmtsLayer) {
    throw new Error("该 WMTS 图层缺少 Layer 标识，无法向服务方声明取哪一层")
  }
  const common = {
    layer: spec.wmtsLayer,
    style: spec.wmtsStyle ?? "default",
    tileMatrixSetID: spec.wmtsTileMatrixSetId ?? "WebMercatorQuad",
    format: spec.wmtsFormat ?? "image/png",
    tilingScheme: tilingSchemeOf(spec),
    credit: spec.attribution,
    maximumLevel: spec.maxZoom,
  }
  if (spec.wmtsTileTemplate) {
    return new Cesium.WebMapTileServiceImageryProvider({
      url: spec.wmtsTileTemplate,
      ...common,
    })
  }
  return new Cesium.WebMapTileServiceImageryProvider({
    url: spec.url,
    ...common,
    dimensions: spec.wmtsDimensions,
  })
}

/** COG：交给服务端渲染成一张图，再作为单幅影像贴上去。 */
function singleImageProvider(spec: LayerSpec): Cesium.ImageryProvider {
  assertMountable(spec)
  return new Cesium.SingleTileImageryProvider({
    url: spec.url,
    credit: spec.attribution,
  })
}

registerLayerType("xyz", (spec) => imageryController(spec, (s) => xyzProvider(s)))
registerLayerType("cog", (spec) => imageryController(spec, (s) => singleImageProvider(s)))
registerLayerType("wmts", (spec) => imageryController(spec, (s) => wmtsProvider(s)))

registerLayerType("terrain", (spec) => ({
  attribution: spec.attribution ?? "",
  async attach(viewer) {
    const globe = viewer as Cesium.Viewer
    const provider = await terrainProvider(spec)
    globe.terrainProvider = provider
    // Cesium 同一时刻只用一个 terrain provider，所以「隐藏」的实现是换回
    // 裸椭球，而不是把 provider 置空 —— 原来保存一份引用就是为了切回来。
    const active: Cesium.TerrainProvider = provider
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
      raise() {},
      lower() {},
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
      raise() {},
      lower() {},
      remove() {
        globe.scene.primitives.remove(tileset)
      },
    } satisfies LayerHandle
  },
}))

function imageryController(
  spec: LayerSpec,
  build: (spec: LayerSpec) => Cesium.ImageryProvider | Promise<Cesium.ImageryProvider>,
) {
  return {
    attribution: spec.attribution ?? "",
    async attach(viewer: unknown): Promise<LayerHandle> {
      const globe = viewer as Cesium.Viewer
      const provider = await resolveImageryProvider(spec, build)
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
        raise() {
          globe.imageryLayers.raise(layer)
        },
        lower() {
          globe.imageryLayers.lower(layer)
        },
        remove() {
          globe.imageryLayers.remove(layer, true)
        },
      }
    },
  }
}

/**
 * ion 影像不走瓦片模板，所以各构建器之前先在这里统一处理一次，
 * 免得每个 handler 都重复一遍 token 检查。
 */
async function resolveImageryProvider(
  spec: LayerSpec,
  build: (spec: LayerSpec) => Cesium.ImageryProvider | Promise<Cesium.ImageryProvider>,
): Promise<Cesium.ImageryProvider> {
  if (spec.url.startsWith("ion://")) {
    if (!token) throw new Error("使用 ion 影像前需要配置访问令牌")
    return Cesium.IonImageryProvider.fromAssetId(assetId(spec.url))
  }
  return build(spec)
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
