/**
 * 绘图种类。
 *
 * 单独成模块而不放进 `globe.ts`：`globe.ts` 会 import Cesium，而测试跑在
 * `node` 环境（见 `vite.config.ts` 的 `test.environment`），Cesium 在那里
 * 没法加载。这与当初把 `georeference.ts` 拆出来是同一个理由。
 */
export const SKETCH_KINDS = ["point", "line", "polygon", "distance", "area", "height"] as const

export type SketchKind = (typeof SKETCH_KINDS)[number]

const LOOKUP: ReadonlySet<string> = new Set(SKETCH_KINDS)

export function isSketchKind(value: string): value is SketchKind {
  return LOOKUP.has(value)
}
