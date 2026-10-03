import type { Job, JobStatus } from "./client"

/**
 * 轮询入库任务直到终态。
 *
 * 单独抽出来是为了能测：轮询的真正难点不是发请求，而是
 * 「什么时候停」「异常时怎么办」「组件卸载了怎么办」这三件事。
 */

export const TERMINAL: readonly JobStatus[] = ["success", "failed", "cancelled"]

export function isTerminal(status: JobStatus): boolean {
  return TERMINAL.includes(status)
}

/** 给界面看的中文状态。失败与取消要能区分——前者要查原因，后者是用户自己点的。 */
export function describeJob(job: Job): { label: string; tone: "wait" | "busy" | "ok" | "bad" } {
  switch (job.status) {
    case "queued":
      return { label: "排队中", tone: "wait" }
    case "running":
      return { label: "正在转 COG", tone: "busy" }
    case "success":
      return { label: "已完成", tone: "ok" }
    case "cancelled":
      return { label: "已取消", tone: "wait" }
    case "failed":
      return { label: job.error ? `失败：${job.error}` : "失败", tone: "bad" }
  }
}

export interface PollOptions {
  /** 单次请求之间的间隔，默认 1.5 秒。 */
  intervalMs?: number
  /** 最多轮询多久，默认 10 分钟——COG 转换是分钟级的，但不该无限等。 */
  timeoutMs?: number
  /** 每次拿到新状态时回调，用于刷新界面。 */
  onUpdate?: (job: Job) => void
  /** 外部中止信号，组件卸载时传。 */
  signal?: AbortSignal
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>
}

export class PollTimeout extends Error {
  constructor(jobId: string) {
    super(`任务 ${jobId} 等待超时，请到任务列表里查看状态`)
    this.name = "PollTimeout"
  }
}

const defaultSleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve) => {
    if (signal?.aborted) {
      resolve()
      return
    }
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener("abort", () => {
      clearTimeout(timer)
      resolve()
    }, { once: true })
  })

/**
 * 反复读任务直到它到终态。
 *
 * 单次读取失败不算终态——网络抖一下不该把用户的任务判成失败，所以继续重试，
 * 但超过总时限就抛 PollTimeout，让人自己去列表里看。
 */
export async function pollJob(
  jobId: string,
  read: (id: string) => Promise<Job>,
  options: PollOptions = {},
): Promise<Job> {
  const interval = options.intervalMs ?? 1500
  const timeout = options.timeoutMs ?? 10 * 60 * 1000
  const sleep = options.sleep ?? defaultSleep
  const deadline = Date.now() + timeout

  for (;;) {
    if (options.signal?.aborted) throw new DOMException("轮询已中止", "AbortError")
    let job: Job
    try {
      job = await read(jobId)
    } catch (error) {
      if (options.signal?.aborted) throw error
      if (Date.now() >= deadline) throw new PollTimeout(jobId)
      await sleep(interval, options.signal)
      continue
    }
    options.onUpdate?.(job)
    if (isTerminal(job.status)) return job
    if (Date.now() >= deadline) throw new PollTimeout(jobId)
    await sleep(interval, options.signal)
  }
}

/** 任务列表里展示用的文件名，没有就用 id 前缀兜底。 */
export function jobTitle(job: Job): string {
  const name = job.payload?.filename
  if (name) return name
  return `任务 ${job.id.slice(0, 8)}`
}
