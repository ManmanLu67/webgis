import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it, beforeEach } from "vitest"
import {
  clampOpacity,
  createLayer,
  registerLayerType,
  resetLayerTypes,
  type LayerSpec,
} from "./layerTypeRegistry"

const here = dirname(fileURLToPath(import.meta.url))

beforeEach(() => {
  resetLayerTypes()
})

describe("图层类型注册表", () => {
  it("拒绝未知类型且不返回控制器", () => {
    expect(() => createLayer({ id: "x", type: "xyz", url: "https://example.invalid/{z}/{x}/{y}.png" })).toThrow(
      /未知图层类型: xyz/,
    )
  })

  it("按登记的类型创建控制器", async () => {
    registerLayerType("xyz", (spec: LayerSpec) => ({
      attribution: spec.attribution ?? "",
      async attach() {
        return {
          attribution: spec.attribution ?? "",
          setShow() {},
          setOpacity() {},
          setMaximumScreenSpaceError() {},
          setSplit() {},
          remove() {},
        }
      },
    }))
    const controller = createLayer({
      id: "base",
      type: "xyz",
      url: "https://example.invalid/{z}/{x}/{y}.png",
      attribution: "示例署名",
    })
    expect(controller.attribution).toBe("示例署名")
  })

  it("把透明度限制在 0 到 1", () => {
    expect(clampOpacity(-1)).toBe(0)
    expect(clampOpacity(2)).toBe(1)
    expect(clampOpacity(Number.NaN)).toBe(1)
    expect(clampOpacity(0.4)).toBe(0.4)
  })

  it("视图核心不点名第三方服务", () => {
    const source = readFileSync(resolve(here, "globe.ts"), "utf8")
    expect(source).not.toMatch(/ion:\/\//)
    expect(source).not.toMatch(/openstreetmap/i)
  })
})
