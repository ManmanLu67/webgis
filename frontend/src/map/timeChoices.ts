/**
 * 选时间这一步该给几条时相。
 *
 * 单独放一个模块而不是留在 `ToolsPanel.vue` 里，是为了能直接测：面板里的逻辑
 * 目前没有组件级测试，混在模板旁边就等于没有覆盖。同 `drapeSources.ts` 的理由。
 *
 * 依据来自后端 `GET /providers` 的 `time_choices`（由 `plugin.yaml` 声明），
 * 前端不认插件 id —— 硬编码插件名正是 docs/SPEC.md §13 记过的那类漂移。
 */

/** `list` 时给多少条可选时相。够挑，又不至于把面板撑得很长。 */
export const TIME_LIST_LIMIT = 12

/** 只列最近一条时的条数。 */
export const TIME_LATEST_LIMIT = 1

export interface TimeChoiceSource {
  time_choices: "latest" | "list" | null
}

/**
 * `latest`（默认）只列一条：在这里选时间只是确认"取哪一景"，而主路径本来就是
 * 最近一景，列一长串反而让人以为要挑。`list` 才给列表 —— 目前只有历史版本源，
 * 因为对它来说"选时间"其实是"选版本"，只剩一条就把这个源废了。
 */
export function timeChoiceLimit(source: TimeChoiceSource): number {
  return source.time_choices === "list" ? TIME_LIST_LIMIT : TIME_LATEST_LIMIT
}