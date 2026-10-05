import type { LayerSpec } from "./layerTypeRegistry"

export type SwipeSource = "local" | "stac" | "wayback"

export interface SwipeScene {
  id: string
  source: SwipeSource
  timeLabel: string
  url: string
  attribution: string
  /** 挂过的完整描述。卷帘重挂时不能只剩 url，否则自定义格网会丢。 */
  spec?: LayerSpec
}

export const DEMO_SCENES: SwipeScene[] = [
  {
    id: "local-2020",
    source: "local",
    timeLabel: "2020-06-01",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "本地入库演示 · © OpenStreetMap 贡献者",
  },
  {
    id: "stac-2021",
    source: "stac",
    timeLabel: "2021-06-01",
    url: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "公开目录演示 · Esri, Maxar, Earthstar Geographics",
  },
  {
    id: "wayback-2014",
    source: "wayback",
    timeLabel: "2014-02-20",
    url: "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    attribution: "历史版本演示 · © OpenStreetMap 贡献者 © CARTO。真实历史版本地址由配置替换，条款以提供方为准。",
  },
]

const SOURCE_LABEL: Record<SwipeSource, string> = {
  local: "本地入库",
  stac: "公开目录",
  wayback: "历史版本",
}

export function sceneOptionLabel(scene: SwipeScene): string {
  return `${SOURCE_LABEL[scene.source]} · ${scene.timeLabel}`
}

export function toLayerSpec(scene: SwipeScene): LayerSpec {
  if (scene.spec) return { ...scene.spec, id: scene.id, show: true, attribution: scene.attribution }
  return {
    id: scene.id,
    type: "xyz",
    url: scene.url,
    attribution: scene.attribution,
    show: true,
  }
}

export function clampSplit(position: number): number {
  if (Number.isNaN(position)) return 0.5
  return Math.min(0.98, Math.max(0.02, position))
}

export function splitFromPointer(clientX: number, left: number, width: number): number {
  if (width <= 0) return 0.5
  return clampSplit((clientX - left) / width)
}

export function hasAllSwipeSources(scenes: SwipeScene[]): boolean {
  const sources = new Set(scenes.map((scene) => scene.source))
  return sources.has("local") && sources.has("stac") && sources.has("wayback")
}
