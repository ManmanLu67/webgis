import { describe, expect, it } from "vitest"
import { parseLayerDate } from "./layerDate"

describe("自选日期", () => {
  it("接受年-月-日", () => {
    expect(parseLayerDate("2026-09-23")).toBe("2026-09-23")
    expect(parseLayerDate(" 2024-02-29 ")).toBe("2024-02-29")
  })

  it("拒绝写错的日期", () => {
    expect(parseLayerDate("2026/09/23")).toBeNull()
    expect(parseLayerDate("2023-02-29")).toBeNull()
    expect(parseLayerDate("")).toBeNull()
  })
})
