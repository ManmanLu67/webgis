import { describe, expect, it } from "vitest"

import {
  RECENT_LIMIT,
  RECENT_VISIBLE,
  forgetLayer,
  readRecentLayers,
  rememberLayer,
  writeRecentLayers,
  type RecentLayer,
} from "./recentLayers"

function layer(id: string, over: Partial<RecentLayer> = {}): RecentLayer {
  return {
    sourceId: "arcgis_wayback",
    id,
    title: `历史 ${id}`,
    time: "2014-02-20",
    attribution: "Esri Wayback",
    layer: { type: "xyz", url: `https://example.invalid/${id}/{z}/{x}/{y}.jpg` },
    ...over,
  }
}

/** 内存版 Storage，够测序列化与容错。 */
function memoryStorage(initial: string | null = null) {
  const data = new Map<string, string>()
  if (initial !== null) data.set("webgis.recentLayers", initial)
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    dump: () => data.get("webgis.recentLayers") ?? null,
  }
}

describe("本机用过的图层", () => {
  it("最新的排在最前", () => {
    const rows = rememberLayer(rememberLayer([], layer("a")), layer("b"))
    expect(rows.map((row) => row.id)).toEqual(["b", "a"])
  })

  it("同一条重复选用只更新位置，不占两条", () => {
    let rows = rememberLayer([], layer("a"))
    rows = rememberLayer(rows, layer("b"))
    rows = rememberLayer(rows, layer("a"))
    expect(rows.map((row) => row.id)).toEqual(["a", "b"])
  })

  it("id 相同但数据源不同视为两条", () => {
    // 否则会出现"加载了另一个源的同名图层"，而界面看不出差别
    const rows = rememberLayer(
      rememberLayer([], layer("x", { sourceId: "arcgis_wayback" })),
      layer("x", { sourceId: "gibs" }),
    )
    expect(rows).toHaveLength(2)
  })

  it("超出上限就丢掉最旧的", () => {
    let rows: RecentLayer[] = []
    for (let i = 0; i < RECENT_LIMIT + 5; i += 1) rows = rememberLayer(rows, layer(`id-${i}`))
    expect(rows).toHaveLength(RECENT_LIMIT)
    expect(rows[0].id).toBe(`id-${RECENT_LIMIT + 4}`)
  })

  it("首屏条数少于总条数，这样「展开」才有意义", () => {
    expect(RECENT_VISIBLE).toBeLessThan(RECENT_LIMIT)
  })

  it("能单独删掉一条", () => {
    const rows = rememberLayer(rememberLayer([], layer("a")), layer("b"))
    expect(forgetLayer(rows, "arcgis_wayback", "a").map((row) => row.id)).toEqual(["b"])
  })

  it("读回来与写进去的一致", () => {
    const storage = memoryStorage()
    writeRecentLayers([layer("a"), layer("b")], storage)
    expect(readRecentLayers(storage).map((row) => row.id)).toEqual(["a", "b"])
  })

  it("存的是完整图层描述，重放不必回后端", () => {
    // 只存 id 的话重放要重新检索；历史版本源的清单每次检索都要下载一秒多
    const storage = memoryStorage()
    writeRecentLayers([layer("a")], storage)
    const [restored] = readRecentLayers(storage)
    expect(restored.layer.url).toContain("{z}")
    expect(restored.attribution).toBe("Esri Wayback")
  })

  it("空存储、坏 JSON、非数组都当没有，不抛", () => {
    expect(readRecentLayers(memoryStorage())).toEqual([])
    expect(readRecentLayers(memoryStorage("not json"))).toEqual([])
    expect(readRecentLayers(memoryStorage('{"a":1}'))).toEqual([])
  })

  it("缺 url 或字段不对的记录被丢掉，不让空图层挂上去", () => {
    const storage = memoryStorage(
      JSON.stringify([
        { sourceId: "s", id: "ok", title: "t", time: "d", attribution: "a", layer: { type: "xyz", url: "u" } },
        { sourceId: "s", id: "no-url", title: "t", time: "d", attribution: "a", layer: { type: "xyz" } },
        { sourceId: "s", id: "no-layer", title: "t", time: "d", attribution: "a" },
        "垃圾数据",
        null,
      ]),
    )
    expect(readRecentLayers(storage).map((row) => row.id)).toEqual(["ok"])
  })
})