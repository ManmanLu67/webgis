import { describe, expect, it } from "vitest"

import { basemapFailureText, checkBasemap } from "./basemapCheck"

const TEMPLATE = "https://tile.example.com/{z}/{x}/{y}.png"

function okFetch() {
  return (async () => ({ ok: true, status: 200 })) as unknown as typeof fetch
}

describe("底图预检", () => {
  it("通得过就算通", async () => {
    const verdict = await checkBasemap({ url: TEMPLATE, fetchImpl: okFetch() })
    expect(verdict).toEqual({ ok: true })
  })

  it("探测的是 z0 的那一格", async () => {
    let requested = ""
    const fetchImpl = (async (url: string) => {
      requested = url
      return { ok: true, status: 200 }
    }) as unknown as typeof fetch
    await checkBasemap({ url: TEMPLATE, fetchImpl })
    expect(requested).toBe("https://tile.example.com/0/0/0.png")
  })

  it("HTTP 失败要说出状态码与主机", async () => {
    // Cesium 自己不报错，所以这里必须把原因说出来，否则地球就是一个空球
    const fetchImpl = (async () => ({ ok: false, status: 403 })) as unknown as typeof fetch
    const verdict = await checkBasemap({ url: TEMPLATE, fetchImpl })
    expect(verdict).toMatchObject({ ok: false, host: "tile.example.com", reason: "HTTP 403" })
    expect(basemapFailureText(verdict as never)).toContain("tile.example.com")
  })

  it("连不上也算失败，而不是放过去", async () => {
    const fetchImpl = (async () => {
      throw new TypeError("Failed to fetch")
    }) as unknown as typeof fetch
    const verdict = await checkBasemap({ url: TEMPLATE, fetchImpl })
    expect(verdict).toMatchObject({ ok: false, host: "tile.example.com", reason: "连不上" })
  })

  it("超时按超时说，不含混成别的错", async () => {
    const fetchImpl = (async (_url: string, init?: RequestInit) => {
      await new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("aborted", "AbortError")),
        )
      })
      return { ok: true, status: 200 }
    }) as unknown as typeof fetch
    const verdict = await checkBasemap({ url: TEMPLATE, fetchImpl, timeoutMs: 1000 })
    expect(verdict).toMatchObject({ ok: false, reason: "1 秒内没有响应" })
  })

  it("ion 地址没有可探测的对象，不算失败", async () => {
    const verdict = await checkBasemap({ url: "ion://2", fetchImpl: okFetch() })
    expect(verdict).toEqual({ ok: true })
  })

  it("地址为空直接说清楚", async () => {
    const verdict = await checkBasemap({ url: "  ", fetchImpl: okFetch() })
    expect(verdict).toMatchObject({ ok: false, reason: "底图地址为空" })
  })

  it("地址不是合法 URL 时不发请求，直接判失败", async () => {
    let called = false
    const fetchImpl = (async () => {
      called = true
      return { ok: true, status: 200 }
    }) as unknown as typeof fetch
    const verdict = await checkBasemap({ url: "{z}/{x}/{y}", fetchImpl })
    expect(verdict.ok).toBe(false)
    expect(called).toBe(false)
    expect(basemapFailureText(verdict as never)).toContain("{z}/{x}/{y}")
  })

  it("通得过不等于有内容——这条限制要写在帮助文本里", () => {
    // 实测存在"通得动但每片都是纯色空白"的源，预检识别不了，只能不假装能识别
    expect(basemapFailureText({ ok: false, host: "h", reason: "r" })).toContain("VITE_IMAGERY_URL")
  })
})