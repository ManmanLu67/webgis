/**
 * 底图预检。
 *
 * 为什么需要：Cesium 的 `UrlTemplateImageryProvider` 在瓦片拉不到时**不抛异常**。
 * 于是 `startGlobe` 照样成功，地球只剩一个没有任何影像的球体，界面什么都不说 ——
 * 表现就是"刷新一下地球没了"，但没有任何线索指向真正的原因。
 * 所以在开球之前先探一次主机通不通，把结果直接说出来。
 *
 * 能力边界（重要）：这个检查只能证明"主机连得上"。它**证明不了瓦片有内容** ——
 * 实测有过通得���、却对每个请求都返回一张纯色空白图的源。所以通了不等于能用，
 * 这里只负责把"连不上"这一种最常见的情况讲清楚。
 */

/** 探测用哪一片。z0 的瓦片最小、最可能被缓存命中，也最容易成功。 */
const PROBE_LEVEL = 0

export interface BasemapCheckInput {
  /** 底图地址模板，含 `{z}/{x}/{y}`。 */
  url: string
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export type BasemapVerdict =
  | { ok: true }
  | { ok: false; host: string; reason: string }

function hostOf(template: string): string {
  try {
    return new URL(template).host || template
  } catch {
    return template
  }
}

/** 没有主机名的模板（例如只剩 `{z}/{x}/{y}`）根本无从探测，别浪费一次请求。 */
function hasUsableUrl(template: string): boolean {
  try {
    return new URL(template).host.length > 0
  } catch {
    return false
  }
}

/**
 * 把模板里的 `{z}/{x}/{y}` 换成 z0 的行列。
 *
 * 只做字面替换，不复用后端那份模板解析：这个模块在浏览器里跑，而后端那份在
 * Python 里。为一个探测请求引入跨语言的模板依赖不值得。
 *
 * 两种网格在 z0 都只有一片瓦片，所以行列取 0 对 WebMercator 与 Geographic
 * 都成立，不需要问投影。
 */
function probeUrl(template: string): string {
  return template.replace(/\{z\}/g, String(PROBE_LEVEL)).replace(/\{x\}/g, "0").replace(/\{y\}/g, "0")
}

export async function checkBasemap(input: BasemapCheckInput): Promise<BasemapVerdict> {
  const template = input.url.trim()
  const host = hostOf(template)
  const doFetch = input.fetchImpl ?? globalThis.fetch
  const timeout = input.timeoutMs ?? 8000

  // ion 地址不走瓦片模板，这里没有可探测的对象，别把它算成失败。
  if (template.startsWith("ion://")) return { ok: true }
  if (!template) return { ok: false, host: "（未配置）", reason: "底图地址为空" }
  if (!hasUsableUrl(template)) {
    return { ok: false, host, reason: "底图地址不是合法的 URL" }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const response = await doFetch(probeUrl(template), { signal: controller.signal })
    if (!response.ok) {
      return { ok: false, host, reason: `HTTP ${response.status}` }
    }
    return { ok: true }
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === "AbortError"
    return {
      ok: false,
      host,
      reason: aborted ? `${timeout / 1000} 秒内没有响应` : "连不上",
    }
  } finally {
    clearTimeout(timer)
  }
}

/** 通不过时给用户看的一句话。 */
export function basemapFailureText(verdict: Extract<BasemapVerdict, { ok: false }>): string {
  return `底图未加载：${verdict.host} ${verdict.reason}。可改 VITE_IMAGERY_URL 换成你有权使用的底图来源。`
}