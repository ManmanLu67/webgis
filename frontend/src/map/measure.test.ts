import { describe, expect, it } from "vitest"
import { formatMeasure, heightMeters, pathDistance } from "./measure"

describe("量算", () => {
  it("赤道上约 1 公里的误差小于 5%", () => {
    const meters = pathDistance([
      { lon: 0, lat: 0 },
      { lon: 1 / 111.32, lat: 0 },
    ])
    expect(Math.abs(meters - 1000) / 1000).toBeLessThan(0.05)
    expect(formatMeasure("distance", meters)).toContain("米")
  })

  it("高度是两点高程差", () => {
    expect(heightMeters(10, 25)).toBe(15)
    expect(formatMeasure("height", 15)).toBe("高度 15 米")
  })
})
