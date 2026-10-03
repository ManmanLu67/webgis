import { describe, expect, it } from "vitest"

import {
  checkGeoreference,
  isGeographic,
  isSupportedGrid,
  SHIFTED_DATUMS,
  SUPPORTED_GRIDS,
} from "./georeference"

describe("瓦片网格", () => {
  it("只认 Cesium 认识的两种网格", () => {
    expect(SUPPORTED_GRIDS).toEqual(["WebMercator", "Geographic"])
    expect(isSupportedGrid("WebMercator")).toBe(true)
    expect(isSupportedGrid("Geographic")).toBe(true)
    expect(isSupportedGrid("EPSG:3857")).toBe(false)
    expect(isSupportedGrid("Gauss-Krüger 3-degree zone 39")).toBe(false)
  })

  it("网格不认识时拒绝挂载并说明原因", () => {
    const verdict = checkGeoreference({ crs: "EPSG:3857", tilingScheme: "EPSG:3857" })
    expect(verdict.ok).toBe(false)
    expect(verdict.reason).toContain("Cesium 只支持")
    expect(verdict.reason).toContain("EPSG:3857")
  })

  it("未声明网格时按 WebMercator 处理", () => {
    expect(checkGeoreference({ crs: "EPSG:3857" }).ok).toBe(true)
    expect(checkGeoreference({}).ok).toBe(true)
  })
})

describe("人为偏移的坐标系", () => {
  it("GCJ-02 一律拒绝，且大小写写法都要拦下", () => {
    for (const spelling of ["GCJ-02", "gcj-02", "GCJ02", "BD-09", "bd09"]) {
      const verdict = checkGeoreference({ crs: spelling, tilingScheme: "WebMercator" })
      expect(verdict.ok, spelling).toBe(false)
      expect(verdict.reason).toContain("人为偏移")
    }
  })

  it("拒绝的理由点名是哪个坐标系，便于界面直接展示", () => {
    expect(checkGeoreference({ crs: "BD-09" }).reason).toContain("BD-09")
    expect(Object.keys(SHIFTED_DATUMS).length).toBeGreaterThan(0)
  })
})

describe("正常坐标系", () => {
  it("WebMercator 网格 + 3857 直接放行", () => {
    expect(checkGeoreference({ crs: "EPSG:3857", tilingScheme: "WebMercator" })).toEqual({
      ok: true,
    })
  })

  it("WebMercator 网格 + CGCS2000 基准放行，并说明无需重投影", () => {
    // 天地图就是这个组合：服务方已经把 CGCS2000 的影像重投影进 Web Mercator 网格了。
    // 基准与网格不是一回事，不能因为 crs 是经纬度就判成错位。
    const verdict = checkGeoreference({ crs: "EPSG:4490", tilingScheme: "WebMercator" })
    expect(verdict.ok).toBe(true)
    expect(verdict.note).toContain("厘米级")
  })

  it("Geographic 网格 + 4326 放行", () => {
    const verdict = checkGeoreference({ crs: "EPSG:4326", tilingScheme: "Geographic" })
    expect(verdict.ok).toBe(true)
    expect(isGeographic("EPSG:4326")).toBe(true)
    expect(isGeographic("EPSG:4490")).toBe(true)
    expect(isGeographic("EPSG:3857")).toBe(false)
  })

  it("未声明坐标系时放行但提示按 WGS84 处理", () => {
    const verdict = checkGeoreference({ tilingScheme: "WebMercator" })
    expect(verdict.ok).toBe(true)
    expect(verdict.note).toContain("未声明坐标系")
  })
})