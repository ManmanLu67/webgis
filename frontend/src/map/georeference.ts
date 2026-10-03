/**
 * 坐标系与瓦片网格的准入判断。
 *
 * 这里要分清两件常被混为一谈的事：
 *
 * - `tilingScheme` 是**瓦片网格**，也就是 URL 模板里 {z}/{x}/{y} 落在哪张格网上。
 *   Cesium 按它摆放瓦片，填错就是错位，所以这是唯一参与渲染决策的字段。
 * - `crs` 是**数据基准**。服务方已经把像素重投影进网格了，浏览器拿到的只是
 *   编码后的图像字节，Cesium 从来看不到原始坐标值。所以 crs 不参与渲染，
 *   只用于署名与合规声明。
 *
 * 因此真正必须拦的只有两类：坐标系经过人为偏移的（GCJ-02 一系，偏移量是数百米，
 * 叠上去必然错位且无法靠网格修正），以及网格是 Cesium 不认识的。
 */

export type GridKind = "WebMercator" | "Geographic"

export const SUPPORTED_GRIDS: readonly GridKind[] = ["WebMercator", "Geographic"]

/**
 * 经过人为偏移的坐标系。这些不是"精度差一点"，而是与 WGS84 差几百米，
 * 且偏移量随地区变化，没有通用的逆变换，只能靠官方提供的转换服务。
 */
export const SHIFTED_DATUMS: Readonly<Record<string, string>> = {
  "GCJ-02": "GCJ-02",
  GCJ02: "GCJ-02",
  "BD-09": "BD-09",
  BD09: "BD-09",
  "GCJ-02 / BD-09": "GCJ-02 / BD-09",
}

/** 同一大地基准下的近似等价基准，差异在厘米级，不影响叠加。 */
const EQUIVALENT_DATUM_NOTE =
  "与 WGS84 属同一大地基准族，差异在厘米级，可直接叠加"

export interface GeoreferenceVerdict {
  ok: boolean
  /** 不通过时给用户看的中文原因 */
  reason?: string
  /** 通过但值得在界面上说清的一句话 */
  note?: string
}

export function checkGeoreference(spec: {
  crs?: string
  tilingScheme?: string
}): GeoreferenceVerdict {
  const crs = (spec.crs ?? "").trim()
  const grid = (spec.tilingScheme ?? "WebMercator").trim()

  const shifted = Object.keys(SHIFTED_DATUMS).find(
    (key) => key.toLowerCase() === crs.toLowerCase(),
  )
  if (shifted) {
    return {
      ok: false,
      reason: `${SHIFTED_DATUMS[shifted]} 相对 WGS84 有数百米的人为偏移，不能直接叠到地球上；请先用官方转换服务重投影`,
    }
  }

  if (!isSupportedGrid(grid)) {
    return {
      ok: false,
      reason: `Cesium 只支持 ${SUPPORTED_GRIDS.join(" 与 ")} 两种瓦片网格，该图层声明的是 ${grid || "未声明"}`,
    }
  }

  if (!crs) {
    return { ok: true, note: "数据源未声明坐标系，默认按 WGS84 处理" }
  }
  if (isGeographic(crs)) {
    return { ok: true, note: `${crs}：${EQUIVALENT_DATUM_NOTE}` }
  }
  return { ok: true }
}

export function isSupportedGrid(grid: string): grid is GridKind {
  return (SUPPORTED_GRIDS as readonly string[]).includes(grid)
}

/** 该 CRS 是否是经纬度坐标系的（含 CGCS2000 等同族基准）。 */
export function isGeographic(crs: string): boolean {
  return /^(EPSG:)?(4326|4490|4258|4269)$/i.test(crs.trim())
}