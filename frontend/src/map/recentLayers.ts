import type { WireLayerSpec } from "../api/layerSpec"

/**
 * 本机用过的图层。
 *
 * 存在 localStorage 而不是目录里：这是"我上次看过哪几景"，属于浏览行为而不是
 * 数据资产。形态照 `bookmarks.ts` —— 纯函数 + 存储注入，所以能直接单测。
 *
 * **连图层描述一起存**，这样再次选用时不必回后端。历史版本源的清单每次检索都要
 * 下载一秒多（现在有缓存，但首次仍要等），而"回到刚才那一景"本该是瞬时的。
 * 存描述顺带把 `attribution` 也存了 —— 署名是展示的硬要求（宪章 C4），
 * 只存 id 的话重放时会丢署名。
 */
export interface RecentLayer {
  /** 数据源 id。重放时要按它决定用哪个图层类型。 */
  sourceId: string
  id: string
  title: string
  time: string
  attribution: string
  layer: WireLayerSpec
}

/** 留多少条。够翻，又不至于把 localStorage 撑大。 */
export const RECENT_LIMIT = 20

/** 首屏显示几条，其余交给「展开」。 */
export const RECENT_VISIBLE = 3

const STORAGE_KEY = "webgis.recentLayers"

function keyOf(layer: Pick<RecentLayer, "sourceId" | "id">): string {
  return `${layer.sourceId}:${layer.id}`
}

/** 最新的排在前面；同一条重复选用只更新位置，不重复占位。 */
export function rememberLayer(recent: RecentLayer[], layer: RecentLayer): RecentLayer[] {
  const key = keyOf(layer)
  return [layer, ...recent.filter((item) => keyOf(item) !== key)].slice(0, RECENT_LIMIT)
}

export function forgetLayer(recent: RecentLayer[], sourceId: string, id: string): RecentLayer[] {
  const key = `${sourceId}:${id}`
  return recent.filter((item) => keyOf(item) !== key)
}

/**
 * 校验一条记录是否可用。
 *
 * localStorage 里的东西可能被手改过，也可能来自旧版本结构，所以逐条检查：
 * 缺 `layer.url` 的记录挂上去只会得到一个空图层，不如当作没有。
 */
function isUsable(value: unknown): value is RecentLayer {
  if (typeof value !== "object" || value === null) return false
  const row = value as Partial<RecentLayer>
  if (typeof row.sourceId !== "string" || typeof row.id !== "string") return false
  if (typeof row.title !== "string" || typeof row.time !== "string") return false
  if (typeof row.attribution !== "string") return false
  if (typeof row.layer !== "object" || row.layer === null) return false
  return typeof (row.layer as WireLayerSpec).url === "string"
}

export function readRecentLayers(storage: Pick<Storage, "getItem"> = localStorage): RecentLayer[] {
  try {
    const parsed: unknown = JSON.parse(storage.getItem(STORAGE_KEY) ?? "[]")
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isUsable).slice(0, RECENT_LIMIT)
  } catch {
    return []
  }
}

export function writeRecentLayers(
  recent: RecentLayer[],
  storage: Pick<Storage, "setItem"> = localStorage,
): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(recent.slice(0, RECENT_LIMIT)))
}