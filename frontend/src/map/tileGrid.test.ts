import { describe, expect, it } from "vitest"

import { serviceLevel, tileGridOf } from "./tileGrid"

describe("瓦片格网", () => {
  it("不声明时就是 Cesium 的 Geographic 默认零级", () => {
    const grid = tileGridOf({ tilingScheme: "Geographic" })
    expect(grid.levelZeroTilesX).toBe(2)
    expect(grid.levelZeroTilesY).toBe(1)
    expect(grid.tilePixelSize).toBe(256)
    expect(grid.levelOffset).toBe(0)
    expect(grid.customLevel).toBe(false)
  })

  it("GIBS 的 4326 格网：10×5 零级、512 像素、级别加 3、最高级 5", () => {
    const grid = tileGridOf({
      tilingScheme: "Geographic",
      levelZeroTilesX: 10,
      levelZeroTilesY: 5,
      levelOffset: 3,
      tilePixelSize: 512,
      maxZoom: 5,
    })
    expect(grid.geographic).toBe(true)
    expect(grid.levelZeroTilesX).toBe(10)
    expect(grid.levelZeroTilesY).toBe(5)
    expect(grid.tilePixelSize).toBe(512)
    expect(grid.maximumLevel).toBe(5)
    expect(grid.customLevel).toBe(true)
    expect(serviceLevel(0, grid)).toBe(3)
    expect(serviceLevel(5, grid)).toBe(8)
  })
})
