import { describe, expect, it } from "vitest"

import { isSketchKind, SKETCH_KINDS } from "./sketchKind"

describe("绘图种类", () => {
  it("认得全部七种", () => {
    expect(SKETCH_KINDS).toEqual(["point", "line", "polygon", "distance", "area", "height"])
    for (const kind of SKETCH_KINDS) {
      expect(isSketchKind(kind), kind).toBe(true)
    }
  })

  it("拒绝拼错的与大小写不同的", () => {
    // 按钮里写 emit('sketch','poitn') 曾经无人拦截
    for (const typo of ["poitn", "Point", "POINt", " points", "points", ""]) {
      expect(isSketchKind(typo), typo).toBe(false)
    }
  })

  it("拒绝不存在的名字", () => {
    for (const name of ["rectangle", "multi_polygon", "measure"]) {
      expect(isSketchKind(name), name).toBe(false)
    }
  })
})
