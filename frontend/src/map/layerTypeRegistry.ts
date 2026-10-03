export const LAYER_TYPES = ["wmts", "xyz", "cog", "terrain", "3dtiles"] as const

export type LayerType = (typeof LAYER_TYPES)[number]

export interface LayerSpec {
  id: string
  type: LayerType
  url: string
  opacity?: number
  show?: boolean
  maximumScreenSpaceError?: number
  attribution?: string
  tilingScheme?: "WebMercator" | "Geographic"
  maxZoom?: number
  layerKind?: "imagery" | "map"
  urlTemplate?: string
  crs?: string
}

export type SplitSide = "left" | "right" | "none"

export interface LayerHandle {
  setShow(show: boolean): void
  setOpacity(opacity: number): void
  setMaximumScreenSpaceError(value: number): void
  setSplit(side: SplitSide): void
  remove(): void
  readonly attribution: string
}

export interface LayerController {
  readonly attribution: string
  attach(viewer: unknown): Promise<LayerHandle>
}

const factories = new Map<LayerType, (spec: LayerSpec) => LayerController>()

export function resetLayerTypes(): void {
  factories.clear()
}

export function registerLayerType(type: LayerType, factory: (spec: LayerSpec) => LayerController): void {
  factories.set(type, factory)
}

export function createLayer(spec: LayerSpec): LayerController {
  const factory = factories.get(spec.type)
  if (!factory) {
    throw new Error(`未知图层类型: ${spec.type}`)
  }
  return factory(spec)
}

export function clampOpacity(value: number): number {
  if (Number.isNaN(value)) return 1
  return Math.min(1, Math.max(0, value))
}
