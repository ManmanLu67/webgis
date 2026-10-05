/**
 * 后端接口的薄封装。
 *
 * 之前 6 个裸 `fetch` 散在两个 .vue 文件里，各自处理错误、各自 `await
 * response.json()` 然后当 any 用。收敛到这里的好处是：错误信息只解析一次
 * （后端统一用 `detail`），失败路径只有一种形状，类型不用在内联位置重复声明。
 *
 * 网关把 `/api` 前缀剥掉，所以这里一律用 `/api/...`；开发期由 vite proxy 转发，
 * 生产期由 Caddy 转发，两边对调用方没有区别。
 */

import type { WireLayerSpec } from "./layerSpec"

/** 后端出错时的形状。FastAPI 的 HTTPException 一律把说明放在 detail。 */
export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, init)
  } catch {
    // 拿不到 response 就没有状态码可言，统一按"连不上"处理。
    // 底层原因（断网、CORS、网关 502）对这个界面来说没有区别。
    throw new ApiError(0, "目录未连接，请确认后端与网关都在运行")
  }
  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }
  if (!response.ok) {
    throw new ApiError(response.status, detailOf(body) ?? `请求失败 HTTP ${response.status}`)
  }
  return body as T
}

/** 从后端的错误响应里取出人能读的说明。导出是为了能单独测它。 */
export function detailOf(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null) return undefined
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === "string") return detail
  // FastAPI 的请求体校验错误是数组，逐条拼成人能读的话
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item as { msg?: unknown }).msg)
      .filter((msg): msg is string => typeof msg === "string")
    if (messages.length) return messages.join("；")
  }
  return undefined
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }
}

// --- 目录 ---

export interface SourceProduct {
  id: string
  title: string
  seam: "daily-seamless" | "daily-gaps" | "composite" | "static"
  seam_label: string
  resolution: string
  dated: boolean
  note: string
}

export interface CatalogSource {
  id: string
  name: string
  mode: string
  status: string
  enabled: boolean
  availability: string
  drape: boolean
  picker: "template" | "extent" | "time" | "recent" | null
  license_note: string
  products?: SourceProduct[]
}

export interface SearchResultItem {
  id: string
  title: string
  time: string
  bbox: number[]
  layer: WireLayerSpec
}

export async function listProviders(): Promise<CatalogSource[]> {
  return request<CatalogSource[]>("/providers")
}

export async function searchProvider(
  providerId: string,
  body: { limit?: number; datetime?: string; bbox?: number[]; template?: unknown; key?: string; product?: string },
): Promise<SearchResultItem[]> {
  // 空 bbox 与"没给范围"同义，不发到线上。`picker: time` 的源（GIBS、Wayback）
  // 不需要范围，而调用方过去用 `bbox ?? []` 兜底，实际发出去的是 `bbox: []`，
  // 后端按"给了范围但长度不对"拒成 400，界面上一点就报"范围需要四个数"。
  const payloadBody = { ...body }
  if (payloadBody.bbox?.length === 0) delete payloadBody.bbox
  const payload = await request<{ items?: SearchResultItem[] }>(
    `/providers/${encodeURIComponent(providerId)}/search`,
    json("POST", payloadBody),
  )
  return payload.items ?? []
}

/**
 * 取某个源的最近一景。
 *
 * 只取一条：选时间这一步只是确认"取哪一景"，而主路径本来就是最近一景，列一长串
 * 反而让人以为要挑。真要指定别的日期，用 ToolsPanel 里的自选日期入口。
 * 不需要挑时间的源走 `picker: recent`，压根不进这一步。
 */
export async function loadTimes(
  providerId: string,
  bbox?: number[],
): Promise<{ id: string; title: string; time: string }[]> {
  const items = await searchProvider(providerId, { limit: 1, bbox })
  return items.map((item) => ({ id: item.id, title: item.title, time: item.time }))
}

export async function layerSpec(
  itemId: string,
  options: { publisher?: string; variant?: string } = {},
): Promise<WireLayerSpec> {
  const query = new URLSearchParams()
  if (options.publisher) query.set("publisher", options.publisher)
  if (options.variant) query.set("variant", options.variant)
  const suffix = query.toString() ? `?${query}` : ""
  return request<WireLayerSpec>(`/items/${encodeURIComponent(itemId)}/layer${suffix}`)
}

// --- 标注 ---

export interface AnnotationFeature {
  type: "Feature"
  id?: string
  geometry: unknown
  properties?: Record<string, unknown>
}

export async function listAnnotations(): Promise<AnnotationFeature[]> {
  const payload = await request<{ features?: AnnotationFeature[] }>("/annotations")
  return payload.features ?? []
}

export async function saveAnnotation(geometry: unknown): Promise<AnnotationFeature> {
  return request<AnnotationFeature>("/annotations", json("POST", { geometry }))
}

/**
 * 删掉一条标注。204 没有响应体，所以不返回值。
 *
 * 只有真正写进目录的标注才有 id 可删：目录未连接时前端会退回到 `crypto.randomUUID()`
 * 生成的本地 id，那种 id 后端查不到，调用它会得到 404。调用方要能区分这两种情况，
 * 所以错误照常往上抛，不在这里吞掉。
 */
export async function deleteAnnotation(annotationId: string): Promise<void> {
  await request<never>(`/annotations/${encodeURIComponent(annotationId)}`, { method: "DELETE" })
}

// --- 入库任务 ---

export type JobStatus = "queued" | "running" | "success" | "failed" | "cancelled"

export interface Job {
  id: string
  type: string
  status: JobStatus
  progress: number
  error: string | null
  payload: { source_path?: string; acquired_at?: string; filename?: string; bytes?: number; item_id?: string }
  created_at: string
  updated_at: string
}

export async function listJobs(params: { status?: JobStatus; limit?: number } = {}): Promise<Job[]> {
  const query = new URLSearchParams()
  if (params.status) query.set("status", params.status)
  if (params.limit !== undefined) query.set("limit", String(params.limit))
  const suffix = query.toString() ? `?${query}` : ""
  return request<Job[]>(`/jobs${suffix}`)
}

export async function readJob(jobId: string): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}`)
}

export async function cancelJob(jobId: string): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" })
}

/** 上传走 multipart，所以不能用 json() 那套。 */
export async function uploadCog(file: File, acquiredAt: string): Promise<Job> {
  const form = new FormData()
  form.append("file", file)
  form.append("acquired_at", acquiredAt)
  return request<Job>("/jobs/uploads", { method: "POST", body: form })
}

// --- 切片耗时 ---

export interface TileTiming {
  duration_ms: number | null
  cache: "none" | "unverified"
  sampled: boolean
  ok?: boolean
  status?: number
  bytes?: number
  server_timing?: string | null
  note: string
}

export async function tileTiming(params: { url: string; z?: number; x?: number; y?: number }): Promise<TileTiming> {
  const query = new URLSearchParams({ url: params.url })
  if (params.z !== undefined) query.set("z", String(params.z))
  if (params.x !== undefined) query.set("x", String(params.x))
  if (params.y !== undefined) query.set("y", String(params.y))
  return request<TileTiming>(`/tiles/timing?${query}`)
}

export type { WireLayerSpec }