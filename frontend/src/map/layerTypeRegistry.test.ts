import { readdirSync, readFileSync } from "node:fs"
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

  it("请求只从 api 层发出，不散在组件里", () => {
    // 之前 6 个裸 fetch 分布在两个 .vue 文件里，各自带一份错误处理。
    // 收敛之后错误解析只有一处，失败路径也只有一种形状。
    const root = resolve(here, "..")
    const offenders: string[] = []
    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = resolve(dir, entry.name)
        if (entry.isDirectory()) {
          walk(full)
          continue
        }
        if (!/\.(ts|vue)$/.test(entry.name) || entry.name.endsWith(".test.ts")) continue
        if (readFileSync(full, "utf8").includes("fetch(")) offenders.push(full)
      }
    }
    walk(root)
    expect(offenders).toEqual([resolve(root, "api", "client.ts")])
  })
})
