/**
 * 弹层里"能铺到地球的数据源"。
 *
 * 判定直接读后端已经算好的 `drape` 与 `availability`——这两个字段由
 * `app/plugins/loader.py` 在加载时校验过，所以这里不需要再猜一遍规则。
 * 需要的密钥、骨架、未实现的源都会被后端排除（宪章 C4：没 Key 不请求）。
 *
 * 类型从 `api/client` 取，避免同一份数据源在前后端各写一遍 interface。
 */
export type { CatalogSource } from "../api/client"

export function layerPickerSources<T extends { drape: boolean; availability: string }>(
  sources: T[],
): T[] {
  return sources.filter((source) => source.drape === true && source.availability === "ready")
}