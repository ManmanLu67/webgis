export const LAYER_TYPES = ["wmts", "xyz", "cog", "terrain", "3dtiles"] as const

export type LayerType = (typeof LAYER_TYPES)[number]

export interface LayerSpec {
  id: string
  type: LayerType
  url: string
  opacity?: number
  show?: boolean
  maximumScreenSpaceError?: number
  attribution?: string
  /** 瓦片网格：Cesium 靠它摆放瓦片，只有它参与渲染决策。 */
  tilingScheme?: "WebMercator" | "Geographic"
  maxZoom?: number
  layerKind?: "imagery" | "map"
  urlTemplate?: string
  /** 数据基准。只用于署名与合规声明，不参与渲染。 */
  crs?: string
  /**
   * WMTS 有两种编码，这里都要能描述。
   *
   * - RESTful：给 `wmtsTileTemplate`（含 `{TileMatrix}/{TileCol}/{TileRow}`），
   *   例如 TiTiler 与 GeoServer GWC 的 RESTful 端点。
   * - KVP：只给基地址 `url`，图层、格网、格式与静态参数分别走
   *   `wmtsLayer` / `wmtsTileMatrixSetId` / `wmtsFormat` / `wmtsDimensions`。
   *   天地图是这一类，且要求 `VERSION=1.0.0` 与 `FORMAT=tiles`。
   */
  wmtsCapabilities?: string
  wmtsLayer?: string
  wmtsTileTemplate?: string
  wmtsStyle?: string
  wmtsTileMatrixSetId?: string
  wmtsFormat?: string
  wmtsDimensions?: Record<string, string>
  /** 需要在界面上说清的重投影 / 基准差异。 */
  georeferenceNote?: string
  /**
   * 非标准 Geographic 格网。默认 2×1、偏移 0、256px 就是 Cesium 的零级。
   * GIBS 的 EPSG:4326 从服务方第 3 级起才是 10×5 的干净金字塔。
   */
  levelZeroTilesX?: number
  levelZeroTilesY?: number
  levelOffset?: number
  tilePixelSize?: number
}

export type SplitSide = "left" | "right" | "none"

export interface LayerHandle {
  setShow(show: boolean): void
  setOpacity(opacity: number): void
  setMaximumScreenSpaceError(value: number): void
  setSplit(side: SplitSide): void
  /** 在同组影像里上移一层。地形和三维瓦片没有影像栈，实现为空。 */
  raise(): void
  /** 在同组影像里下移一层。 */
  lower(): void
  remove(): void
  readonly attribution: string
}

export interface LayerController {
  readonly attribution: string
  attach(viewer: unknown): Promise<LayerHandle>
}

const factories = new Map<LayerType, (spec: LayerSpec) => LayerController>()

export function resetLayerTypes(): void {
  factories.clear()
}

export function registerLayerType(type: LayerType, factory: (spec: LayerSpec) => LayerController): void {
  factories.set(type, factory)
}

export function createLayer(spec: LayerSpec): LayerController {
  const factory = factories.get(spec.type)
  if (!factory) {
    throw new Error(`未知图层类型: ${spec.type}`)
  }
  return factory(spec)
}

export function clampOpacity(value: number): number {
  if (Number.isNaN(value)) return 1
  return Math.min(1, Math.max(0, value))
}
