import { describe, expect, it } from "vitest"
import { DEMO_SCENES, clampSplit, hasAllSwipeSources, sceneOptionLabel, splitFromPointer } from "./swipe"

describe("卷帘", () => {
  it("把分割位置限制在画面内", () => {
    expect(clampSplit(-1)).toBe(0.02)
    expect(clampSplit(2)).toBe(0.98)
    expect(clampSplit(Number.NaN)).toBe(0.5)
    expect(clampSplit(0.25)).toBe(0.25)
  })

  it("用指针位置换算分割比例", () => {
    expect(splitFromPointer(250, 0, 1000)).toBe(0.25)
    expect(splitFromPointer(0, 0, 0)).toBe(0.5)
  })

  it("演示列表含三种来源且标签可区分", () => {
    expect(hasAllSwipeSources(DEMO_SCENES)).toBe(true)
    const labels = DEMO_SCENES.map(sceneOptionLabel)
    expect(labels.some((label) => label.startsWith("本地入库"))).toBe(true)
    expect(labels.some((label) => label.startsWith("公开目录"))).toBe(true)
    expect(labels.some((label) => label.startsWith("历史版本"))).toBe(true)
  })
})
