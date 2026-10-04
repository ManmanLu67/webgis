import { describe, expect, it, vi } from "vitest"

import { ApiError, detailOf } from "./client"

/** 把 fetch 换成可控的假实现，逐个检查请求的形状与错误的处理。 */
type FetchCall = [string, RequestInit | undefined]

function stubFetch(body: unknown, status = 200) {
  const calls: FetchCall[] = []
  const spy = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push([url, init])
    return {
      ok: status >= 200 && status < 300,
      status,
      text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
    } as unknown as Response
  })
  vi.stubGlobal("fetch", spy)
  return { spy, calls }
}

describe("请求前缀", () => {
  it("一律走 /api 前缀，由网关或 vite proxy 转发", async () => {
    const { calls } = stubFetch([])
    const { listProviders } = await import("./client")
    await listProviders()
    expect(calls[0][0]).toBe("/api/providers")
  })

  it("条目 id 与 provider id 做 URL 编码", async () => {
    const { calls } = stubFetch({ items: [] })
    const { searchProvider } = await import("./client")
    await searchProvider("weird id/../x", { limit: 1 })
    expect(calls[0][0]).toBe("/api/providers/weird%20id%2F..%2Fx/search")
  })

  it("上传走 multipart，不手写 Content-Type", async () => {
    // 手写 multipart 的 boundary 会与浏览器自己生成的那个冲突
    const { calls } = stubFetch({ id: "j", status: "queued", payload: {} })
    const { uploadCog } = await import("./client")
    await uploadCog(new File(["x"], "a.tif"), "2024-01-01T00:00:00Z")
    const init = calls[0][1] as RequestInit
    expect(init.method).toBe("POST")
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.headers ?? {}).not.toHaveProperty("Content-Type")
  })
})

describe("错误处理", () => {
  it("把 FastAPI 的 detail 变成 Error.message", async () => {
    stubFetch({ detail: "未知数据源" }, 404)
    const { searchProvider } = await import("./client")
    await expect(searchProvider("nope", {})).rejects.toThrow("未知数据源")
  })

  it("带上 HTTP 状态码，便于界面区分对待", async () => {
    stubFetch({ detail: "未实现" }, 501)
    const { searchProvider } = await import("./client")
    await expect(searchProvider("jilin1", {})).rejects.toMatchObject({ status: 501 })
  })

  it("校验错误数组拼成人能读的话", () => {
    expect(
      detailOf({ detail: [{ msg: "field required" }, { msg: "wrong type" }] }),
    ).toBe("field required；wrong type")
  })

  it("没有 detail 时退回状态码说明", async () => {
    stubFetch("网关错误", 502)
    const { listProviders } = await import("./client")
    await expect(listProviders()).rejects.toThrow("请求失败 HTTP 502")
  })

  it("非 JSON 响应不会把解析异常漏给调用方", async () => {
    stubFetch("<html>502</html>", 502)
    const { listProviders } = await import("./client")
    await expect(listProviders()).rejects.toBeInstanceOf(ApiError)
  })

  it("连不上时说的是连接问题，不是 HTTP 错误", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch")
    }))
    const { listProviders } = await import("./client")
    await expect(listProviders()).rejects.toThrow("目录未连接")
    await expect(listProviders()).rejects.toMatchObject({ status: 0 })
  })

  it("响应体缺失或形状不对时返回 undefined 而不是抛", () => {
    expect(detailOf(null)).toBeUndefined()
    expect(detailOf("")).toBeUndefined()
    expect(detailOf({})).toBeUndefined()
    expect(detailOf({ detail: 42 })).toBeUndefined()
  })
})

describe("检索请求的范围参数", () => {
  /** 把 POST 的 JSON 取出��，看 bbox 字段到底有没有上线。 */
  function sentBody(call: FetchCall | undefined): Record<string, unknown> {
    return JSON.parse(String((call?.[1] as RequestInit).body)) as Record<string, unknown>
  }

  it("空 bbox 不上线：picker 为 time 的源本来就不需要范围", async () => {
    // 过去这里是 `bbox ?? []`，发出去的是 `bbox: []`，后端判成"长度不对"而 400。
    const { calls } = stubFetch({ items: [] })
    const { loadTimes } = await import("./client")
    await loadTimes("gibs", [])
    expect(sentBody(calls[0])).not.toHaveProperty("bbox")
    expect(calls[0][0]).toBe("/api/providers/gibs/search")
  })

  it("不给 bbox 与给空 bbox 发出的请求完全一样", async () => {
    const { calls } = stubFetch({ items: [] })
    const { loadTimes } = await import("./client")
    await loadTimes("gibs")
    await loadTimes("gibs", [])
    expect(sentBody(calls[0])).toEqual(sentBody(calls[1]))
  })

  it("真实的四元组照发不误，public_stac 仍拿得到范围", async () => {
    const { calls } = stubFetch({ items: [] })
    const { loadTimes } = await import("./client")
    await loadTimes("public_stac", [116, 39, 117, 40])
    expect(sentBody(calls[0]).bbox).toEqual([116, 39, 117, 40])
  })
})

describe("标注删除", () => {
  it("按契约发 DELETE，204 不带响应体", async () => {
    // 契约 specs/005-map-tools/contracts/annotations.openapi.yaml：
    // DELETE /annotations/{annotation_id} → 204
    const { calls } = stubFetch("", 204)
    const { deleteAnnotation } = await import("./client")
    await expect(deleteAnnotation("abc123")).resolves.toBeUndefined()
    expect(calls[0][0]).toBe("/api/annotations/abc123")
    expect((calls[0][1] as RequestInit).method).toBe("DELETE")
  })

  it("标注 id 做 URL 编码", async () => {
    const { calls } = stubFetch("", 204)
    const { deleteAnnotation } = await import("./client")
    await deleteAnnotation("a/../b")
    expect(calls[0][0]).toBe("/api/annotations/a%2F..%2Fb")
  })

  it("后端拒绝时如实抛出，不把失败当成已删除", async () => {
    // 目录未连接时标注只有本地 id，删不到就是删不到，界面要能说出这件事
    stubFetch({ detail: "未知标注" }, 404)
    const { deleteAnnotation } = await import("./client")
    await expect(deleteAnnotation("local-only")).rejects.toThrow("未知标注")
  })
})

describe("任务查询参数", () => {
  it("只带上确实给了的可选项", async () => {
    const { calls } = stubFetch([])
    const { listJobs } = await import("./client")
    await listJobs()
    await listJobs({ status: "queued", limit: 5 })
    expect(calls[0][0]).toBe("/api/jobs")
    expect(calls[1][0]).toBe("/api/jobs?status=queued&limit=5")
  })

  it("耗时采样把 COG 地址带上", async () => {
    const { calls } = stubFetch({ duration_ms: 1, cache: "none", sampled: true, note: "" })
    const { tileTiming } = await import("./client")
    await tileTiming({ url: "C:/data/a b.tif", z: 3, x: 1, y: 2 })
    expect(calls[0][0]).toBe("/api/tiles/timing?url=C%3A%2Fdata%2Fa+b.tif&z=3&x=1&y=2")
  })
})
