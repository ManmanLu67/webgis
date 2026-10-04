import { describe, expect, it } from "vitest"

import { attributionOf, toMountableLayer, type WireLayerSpec } from "./layerSpec"

describe("线上图层描述转换", () => {
  it("XYZ 图层带上网格与级别", () => {
    const spec = toMountableLayer(
      {
        id: "a:xyz",
        type: "xyz",
        url: "/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=x",
        tiling_scheme: "WebMercator",
        max_zoom: 12,
        crs: "EPSG:3857",
        attribution: "本平台",
      },
      "fallback",
    )
    expect(spec.type).toBe("xyz")
    expect(spec.tilingScheme).toBe("WebMercator")
    expect(spec.maxZoom).toBe(12)
    expect(spec.crs).toBe("EPSG:3857")
    expect(spec.attribution).toBe("本平台")
  })

  it("RESTful WMTS 带上瓦片模板与图层标识", () => {
    const spec = toMountableLayer(
      {
        type: "wmts",
        url: "/cog/WMTSCapabilities.xml?url=x&use_epsg=true",
        wmts_capabilities: "/cog/WMTSCapabilities.xml?url=x&use_epsg=true",
        wmts_layer: "job42_WebMercatorQuad_default",
        wmts_tile_template: "/cog/tiles/WebMercatorQuad/{TileMatrix}/{TileCol}/{TileRow}.png?url=x",
        wmts_tile_matrix_set_id: "WebMercatorQuad",
      },
      "fallback",
    )
    expect(spec.type).toBe("wmts")
    expect(spec.wmtsTileTemplate).toContain("{TileMatrix}")
    expect(spec.wmtsLayer).toBe("job42_WebMercatorQuad_default")
    expect(spec.wmtsTileMatrixSetId).toBe("WebMercatorQuad")
  })

  it("KVP WMTS 带上基地址、格网、格式与静态参数", () => {
    const spec = toMountableLayer(
      {
        type: "wmts",
        url: "https://t0.tianditu.gov.cn/img_w/wmts",
        wmts_layer: "img",
        wmts_style: "default",
        wmts_tile_matrix_set_id: "w",
        wmts_format: "tiles",
        wmts_dimensions: { tk: "secret" },
        crs: "EPSG:4490",
        georeference_note: "CGCS2000 基准",
      },
      "fallback",
    )
    expect(spec.type).toBe("wmts")
    expect(spec.wmtsTileTemplate).toBeUndefined()
    expect(spec.url).toBe("https://t0.tianditu.gov.cn/img_w/wmts")
    expect(spec.wmtsDimensions).toEqual({ tk: "secret" })
    expect(spec.wmtsFormat).toBe("tiles")
    expect(spec.georeferenceNote).toBe("CGCS2000 基准")
  })

  it("cog 图层保持为单幅影像类型，不被当成 XYZ 模板", () => {
    const spec = toMountableLayer({ type: "cog", url: "/cog/preview?url=x" }, "fallback")
    expect(spec.type).toBe("cog")
    expect(spec.url).toBe("/cog/preview?url=x")
  })

  it("不认识或缺失的类型退回 xyz，并丢掉不该有的网格声明", () => {
    const spec = toMountableLayer({ type: "wms", url: "u", tiling_scheme: "EPSG:3857", max_zoom: null }, "f")
    expect(spec.type).toBe("xyz")
    expect(spec.tilingScheme).toBeUndefined()
    expect(spec.maxZoom).toBeUndefined()
  })

  it("缺 id 时用调用方给的兜底值", () => {
    expect(toMountableLayer({ url: "u" }, "job42").id).toBe("job42")
  })

  it("空字符串与 null 一律不写进结果，避免覆盖掉 Cesium 的默认值", () => {
    const spec = toMountableLayer(
      { url: "u", attribution: "", url_template: null, wmts_layer: null, crs: "" },
      "f",
    )
    expect(spec.attribution).toBeUndefined()
    expect(spec.urlTemplate).toBeUndefined()
    expect(spec.wmtsLayer).toBeUndefined()
    expect(spec.crs).toBeUndefined()
  })

  it("非字符串的静态参数被剔掉", () => {
    const spec = toMountableLayer(
      { type: "wmts", url: "u", wmts_layer: "img", wmts_dimensions: { tk: "k", n: 3 } as never },
      "f",
    )
    expect(spec.wmtsDimensions).toEqual({ tk: "k" })
  })
})

describe("署名取值", () => {
  const base: WireLayerSpec = { attribution: "", license_note: "" }

  it("优先服务方要求的署名", () => {
    expect(attributionOf({ attribution: "天地图，审图号 X", license_note: "条款" })).toBe(
      "天地图，审图号 X",
    )
  })

  it("没有署名时退回授权声明", () => {
    expect(attributionOf({ ...base, license_note: "NASA GIBS 公开数据" })).toBe("NASA GIBS 公开数据")
  })

  it("都没有时用调用方给的兜底值", () => {
    expect(attributionOf(base, "用户自备地址")).toBe("用户自备地址")
  })

  it("只有空白字符时视为没有", () => {
    expect(attributionOf({ attribution: "   ", license_note: "  " }, "兜底")).toBe("兜底")
  })
})

describe("有效覆盖范围", () => {
  const gibs = { type: "xyz", url: "u", tiling_scheme: "WebMercator" } as WireLayerSpec

  it("四元组收成矩形，交给 Cesium 去裁掉没有数据的格子", () => {
    const spec = toMountableLayer({ ...gibs, coverage_bbox: [-180, -85, 180, 85] }, "f")
    expect(spec.coverage).toEqual({ west: -180, south: -85, east: 180, north: 85 })
  })

  it("没声明就是整张网格都有数据，不去裁剪", () => {
    expect(toMountableLayer(gibs, "f").coverage).toBeUndefined()
    expect(toMountableLayer({ ...gibs, coverage_bbox: null }, "f").coverage).toBeUndefined()
  })

  it("长度不对或不是数字时当没声明", () => {
    // 宁可不去裁剪，也不要拿一个错的矩形把该显示的地方也切掉
    expect(toMountableLayer({ ...gibs, coverage_bbox: [-180, -85] }, "f").coverage).toBeUndefined()
    expect(
      toMountableLayer({ ...gibs, coverage_bbox: [-180, -85, 0, 0, 5] }, "f").coverage,
    ).toBeUndefined()
    expect(
      toMountableLayer({ ...gibs, coverage_bbox: ["a", 0, 1, 2] as never }, "f").coverage,
    ).toBeUndefined()
    expect(
      toMountableLayer({ ...gibs, coverage_bbox: [Number.NaN, 0, 1, 2] }, "f").coverage,
    ).toBeUndefined()
  })

  it("西经大于东经、南纬大于北纬的矩形一律拒绝", () => {
    expect(toMountableLayer({ ...gibs, coverage_bbox: [10, -5, -10, 5] }, "f").coverage).toBeUndefined()
    expect(toMountableLayer({ ...gibs, coverage_bbox: [-10, 5, 10, -5] }, "f").coverage).toBeUndefined()
  })

  it("零面积的矩形也拒绝", () => {
    expect(toMountableLayer({ ...gibs, coverage_bbox: [0, 0, 0, 10] }, "f").coverage).toBeUndefined()
  })
})