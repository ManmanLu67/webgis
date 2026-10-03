import { describe, expect, it } from "vitest"
import { groupLayers, moveLayer, withoutLayer, type ManagedLayer } from "./layers"

const sample: ManagedLayer[] = [
  { id: "a", name: "甲", group: "底图", visible: true, opacity: 1, order: 0 },
  { id: "b", name: "乙", group: "底图", visible: true, opacity: 1, order: 1 },
  { id: "c", name: "丙", group: "地形", visible: true, opacity: 1, order: 2 },
]

describe("图层列表", () => {
  it("按数据源分组", () => {
    const groups = groupLayers(sample)
    expect(groups.map((group) => group.group)).toEqual(["底图", "地形"])
    expect(groups[0].layers.map((layer) => layer.id)).toEqual(["a", "b"])
  })

  it("下移交换顺序，到头则不变", () => {
    const moved = moveLayer(sample, "a", "down")
    expect(moved.find((layer) => layer.id === "a")?.order).toBe(1)
    expect(moveLayer(sample, "c", "down")).toBe(sample)
  })

  it("删除后不再出现", () => {
    expect(withoutLayer(sample, "b").map((layer) => layer.id)).toEqual(["a", "c"])
  })
})
