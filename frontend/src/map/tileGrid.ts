import type { LayerSpec } from "./layerTypeRegistry"

/**
 * 把图层描述收成 Cesium 建格网时要的那几个数。
 *
 * 单独拿出来是因为这几个数一错就是整片平移：零级行列、瓦片像素、
 * 以及 URL 级别相对 Cesium 级别的偏移。不依赖 Cesium，测试可以直接断言。
 */
export interface TileGrid {
  geographic: boolean
  levelZeroTilesX: number
  levelZeroTilesY: number
  levelOffset: number
  tilePixelSize: number
  maximumLevel: number | undefined
  /** 偏移不为 0 时，URL 里的级别不能用 Cesium 的 `{z}`，要走自定义标签。 */
  customLevel: boolean
}

export function tileGridOf(spec: Pick<
  LayerSpec,
  "tilingScheme" | "levelZeroTilesX" | "levelZeroTilesY" | "levelOffset" | "tilePixelSize" | "maxZoom"
>): TileGrid {
  const levelOffset = spec.levelOffset ?? 0
  return {
    geographic: spec.tilingScheme === "Geographic",
    levelZeroTilesX: spec.levelZeroTilesX ?? 2,
    levelZeroTilesY: spec.levelZeroTilesY ?? 1,
    levelOffset,
    tilePixelSize: spec.tilePixelSize ?? 256,
    maximumLevel: spec.maxZoom,
    customLevel: levelOffset !== 0,
  }
}

/** URL 里实际请求的级别。Cesium 从 0 数，服务方可能从更高的一级才对齐。 */
export function serviceLevel(cesiumLevel: number, grid: TileGrid): number {
  return cesiumLevel + grid.levelOffset
}
