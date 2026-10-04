import { describe, expect, it } from "vitest"

import { TIME_LATEST_LIMIT, TIME_LIST_LIMIT, timeChoiceLimit } from "./timeChoices"

describe("选时间时列几条", () => {
  it("默认只给最近一条", () => {
    // GIBS 与公开目录的"选时间"只是确认取哪一景，主路径就是最近一景
    expect(timeChoiceLimit({ time_choices: "latest" })).toBe(TIME_LATEST_LIMIT)
  })

  it("没声明也按最近一条算，不给面板一个空的判断分支", () => {
    expect(timeChoiceLimit({ time_choices: null })).toBe(TIME_LATEST_LIMIT)
  })

  it("历史版本源要给列表，否则等于把这个源废了", () => {
    // 对它来说"选时间"其实是"选版本"，只剩一条就没有版本可选了
    expect(timeChoiceLimit({ time_choices: "list" })).toBe(TIME_LIST_LIMIT)
    expect(TIME_LIST_LIMIT).toBeGreaterThan(TIME_LATEST_LIMIT)
  })

  it("列出的条数是可观的，不至于把面板撑爆", () => {
    expect(TIME_LIST_LIMIT).toBeLessThanOrEqual(20)
  })
})