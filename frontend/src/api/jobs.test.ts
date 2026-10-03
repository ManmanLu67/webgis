import { describe, expect, it, vi } from "vitest"

import type { Job, JobStatus } from "./client"
import { describeJob, isTerminal, jobTitle, PollTimeout, pollJob } from "./jobs"

function job(status: JobStatus, extra: Partial<Job> = {}): Job {
  return {
    id: "job1",
    type: "ingest",
    status,
    progress: 0,
    error: null,
    payload: {},
    created_at: "2024-01-01T00:00:00+00:00",
    updated_at: "2024-01-01T00:00:00+00:00",
    ...extra,
  }
}

const noSleep = () => Promise.resolve()

describe("终态判定", () => {
  it("queued 与 running 都还要继续等", () => {
    expect(isTerminal("queued")).toBe(false)
    expect(isTerminal("running")).toBe(false)
  })

  it("success / failed / cancelled 都算结束", () => {
    expect(isTerminal("success")).toBe(true)
    expect(isTerminal("failed")).toBe(true)
    expect(isTerminal("cancelled")).toBe(true)
  })
})

describe("状态文案", () => {
  it("区分排队与转换中", () => {
    expect(describeJob(job("queued"))).toEqual({ label: "排队中", tone: "wait" })
    expect(describeJob(job("running"))).toEqual({ label: "正在转 COG", tone: "busy" })
  })

  it("失败时把原因带上", () => {
    expect(describeJob(job("failed", { error: "不是影像文件" })).label).toBe("失败：不是影像文件")
    expect(describeJob(job("failed")).label).toBe("失败")
  })

  it("取消与失败在界面上不是一回事", () => {
    expect(describeJob(job("cancelled")).tone).not.toBe(describeJob(job("failed")).tone)
  })
})

describe("轮询", () => {
  it("到终态就停，并回调每一次的新状态", async () => {
    const sequence = [job("queued"), job("running"), job("success")]
    const read = vi.fn(async () => sequence.shift() as Job)
    const seen: JobStatus[] = []
    const result = await pollJob("job1", read, { onUpdate: (j) => seen.push(j.status), sleep: noSleep })
    expect(result.status).toBe("success")
    expect(seen).toEqual(["queued", "running", "success"])
    expect(read).toHaveBeenCalledTimes(3)
  })

  it("任务一上来就是终态时只查一次", async () => {
    const read = vi.fn(async () => job("failed", { error: "不是影像文件" }))
    const result = await pollJob("job1", read, { sleep: noSleep })
    expect(result.status).toBe("failed")
    expect(read).toHaveBeenCalledTimes(1)
  })

  it("单次读取失败不算终态，继续重试", async () => {
    let calls = 0
    const read = vi.fn(async () => {
      calls += 1
      if (calls === 1) throw new Error("网络抖了一下")
      return job("success")
    })
    const result = await pollJob("job1", read, { sleep: noSleep })
    expect(result.status).toBe("success")
    expect(read).toHaveBeenCalledTimes(2)
  })

  it("一直读不出来就超时，不无限等", async () => {
    const read = vi.fn(async () => {
      throw new Error("连不上")
    })
    await expect(
      pollJob("job1", read, { sleep: noSleep, intervalMs: 0, timeoutMs: 0 }),
    ).rejects.toBeInstanceOf(PollTimeout)
  })

  it("超时提示里带任务号，让人能自己去列表里找", async () => {
    const read = vi.fn(async () => job("running"))
    const error = await pollJob("abc123def456", read, { sleep: noSleep, timeoutMs: 0 }).catch((e) => e)
    expect(error).toBeInstanceOf(PollTimeout)
    expect((error as Error).message).toContain("abc123def456")
  })

  it("组件卸载后立即中止，不再发请求", async () => {
    const controller = new AbortController()
    const read = vi.fn(async () => job("running"))
    const pending = pollJob("job1", read, { sleep: noSleep, signal: controller.signal })
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: "AbortError" })
  })
})

describe("任务标题", () => {
  it("优先用上传时的文件名", () => {
    expect(jobTitle(job("queued", { payload: { filename: "scene.tif" } }))).toBe("scene.tif")
  })

  it("没有文件名时用 id 前缀兜底", () => {
    expect(jobTitle(job("queued", { id: "0123456789abcdef" }))).toBe("任务 01234567")
  })
})