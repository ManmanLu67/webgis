<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { attributionOf, toMountableLayer, type WireLayerSpec } from "./api/layerSpec"
import { resolveGlobeConfig } from "./config"
import { configureCesium } from "./map/cesiumLayers"
import { asGeoGeometry, startGlobe, type GeoGeometry, type GlobeHandles } from "./map/globe"
import { DEMO_SCENES, splitFromPointer, toLayerSpec, type SwipeScene } from "./map/swipe"
import type { LayerHandle } from "./map/layerTypeRegistry"
import { addBookmark, coordinateError, readBookmarks, writeBookmarks, type Bookmark } from "./map/bookmarks"
import { moveLayer, withoutLayer, type ManagedLayer } from "./map/layers"
import ToolsPanel from "./ToolsPanel.vue"

const config = resolveGlobeConfig(import.meta.env)
const attribution = ref(config.imagery.attribution)
const imageryOn = ref(true)
const terrainOn = ref(true)
const tilesetOn = ref(true)
const opacity = ref(1)
const errorText = ref(0)
const screenError = ref(config.tileset.maximumScreenSpaceError ?? 16)
const tilesetConfigured = config.tileset.url.length > 0
const scenes = ref<SwipeScene[]>([...DEMO_SCENES])
const swipeOn = ref(false)
const split = ref(0.5)
const leftId = ref("local-2020")
const rightId = ref("stac-2021")
const toolMessage = ref("")
const sketching = ref(false)
const measureText = ref("")
const bookmarks = ref<Bookmark[]>(readBookmarks())
const flyLon = ref(116)
const flyLat = ref(40)
const bookmarkName = ref("北京")
const annotations = ref<{ id?: string; geometry: GeoGeometry }[]>([])
const sources = ref<{ id: string; name: string; availability: string; drape: boolean; picker: "time" | "extent" | "template" | null }[]>([])
const xyzName = ref("")
const xyzUrl = ref("")
const xyzScheme = ref("WebMercator")
const xyzKind = ref("imagery")
const xyzZoom = ref(18)
const xyzTime = ref("")
const managedLayers = ref<ManagedLayer[]>([
  { id: "imagery", name: "全球影像", group: "底图", visible: true, opacity: 1, order: 0 },
  { id: "terrain", name: "地形", group: "地形", visible: true, opacity: 1, order: 1 },
])
const extraLayers = new Map<string, LayerHandle>()
let handles: GlobeHandles | null = null
let swipeLeft: LayerHandle | null = null
let swipeRight: LayerHandle | null = null

function sceneById(id: string): SwipeScene {
  return scenes.value.find((scene) => scene.id === id) ?? scenes.value[0]
}

onMounted(async () => {
  const node = document.getElementById("cesium")
  if (!node) return
  configureCesium({ token: config.ionToken })
  try {
    handles = await startGlobe(node, config)
    attribution.value = [handles.imagery.attribution, handles.tileset?.attribution ?? ""].filter(Boolean).join(" · ")
    await loadAnnotations()
    await loadSources()
  } catch (error) {
    errorText.value = 1
    attribution.value = error instanceof Error ? error.message : "地球加载失败"
  }
})

watch(imageryOn, (show) => {
  if (!swipeOn.value) handles?.imagery.setShow(show)
})
watch(terrainOn, (show) => handles?.terrain.setShow(show))
watch(tilesetOn, (show) => handles?.tileset?.setShow(show))
watch(opacity, (value) => handles?.imagery.setOpacity(value))
watch(screenError, (value) => handles?.tileset?.setMaximumScreenSpaceError(value))

watch(swipeOn, async (enabled) => {
  if (!handles) return
  if (!enabled) {
    swipeLeft?.remove()
    swipeRight?.remove()
    swipeLeft = null
    swipeRight = null
    handles.imagery.setShow(imageryOn.value)
    attribution.value = [handles.imagery.attribution, handles.terrain.attribution, handles.tileset?.attribution ?? ""]
      .filter(Boolean)
      .join(" · ")
    return
  }
  handles.imagery.setShow(false)
  split.value = 0.5
  handles.setSplitPosition(0.5)
  swipeLeft = await handles.mountSwipeSide(toLayerSpec(sceneById(leftId.value)), "left")
  swipeRight = await handles.mountSwipeSide(toLayerSpec(sceneById(rightId.value)), "right")
  attribution.value = `${swipeLeft.attribution} · ${swipeRight.attribution}`
})

watch(leftId, async (id) => {
  if (!swipeOn.value || !handles) return
  swipeLeft?.remove()
  swipeLeft = await handles.mountSwipeSide(toLayerSpec(sceneById(id)), "left")
  if (swipeRight) attribution.value = `${swipeLeft.attribution} · ${swipeRight.attribution}`
})

watch(rightId, async (id) => {
  if (!swipeOn.value || !handles) return
  swipeRight?.remove()
  swipeRight = await handles.mountSwipeSide(toLayerSpec(sceneById(id)), "right")
  if (swipeLeft) attribution.value = `${swipeLeft.attribution} · ${swipeRight.attribution}`
})

async function onLayerVisible(id: string, visible: boolean): Promise<void> {
  managedLayers.value = managedLayers.value.map((layer) => (layer.id === id ? { ...layer, visible } : layer))
  if (id === "imagery") {
    imageryOn.value = visible
    return
  }
  if (id === "terrain") {
    terrainOn.value = visible
    return
  }
  const scene = DEMO_SCENES.find((item) => item.id === id)
  if (!scene || !handles) return
  let handle = extraLayers.get(id)
  if (visible && !handle) {
    handle = await handles.mountSwipeSide(toLayerSpec(scene), "none")
    extraLayers.set(id, handle)
  }
  handle?.setShow(visible)
}

function onLayerOpacity(id: string, opacityValue: number): void {
  managedLayers.value = managedLayers.value.map((layer) =>
    layer.id === id ? { ...layer, opacity: opacityValue } : layer,
  )
  if (id === "imagery") {
    opacity.value = opacityValue
    return
  }
  extraLayers.get(id)?.setOpacity(opacityValue)
}

function onLayerMove(id: string, direction: "up" | "down"): void {
  managedLayers.value = moveLayer(managedLayers.value, id, direction)
}

function onLayerRemove(id: string): void {
  if (id === "imagery") handles?.imagery.setShow(false)
  else if (id === "terrain") handles?.terrain.setShow(false)
  else extraLayers.get(id)?.remove()
  extraLayers.delete(id)
  managedLayers.value = withoutLayer(managedLayers.value, id)
}

function onSketch(kind: string): void {
  sketching.value = true
  toolMessage.value = ""
  handles?.beginSketch(kind as "point")
}

async function onFinish(): Promise<void> {
  const result = handles?.finishSketch()
  if (!result) return
  if (result.message) {
    toolMessage.value = result.message
    return
  }
  sketching.value = false
  if (result.text) {
    measureText.value = result.text
    toolMessage.value = ""
    return
  }
  if (!result.geometry) return
  const localId = crypto.randomUUID()
  handles?.showAnnotation(localId, result.geometry)
  try {
    const response = await fetch("/api/annotations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ geometry: result.geometry }),
    })
    if (!response.ok) throw new Error("保存失败")
    const feature = await response.json()
    annotations.value = [...annotations.value, feature]
    toolMessage.value = "已写入目录"
  } catch {
    annotations.value = [...annotations.value, { id: localId, geometry: result.geometry }]
    toolMessage.value = "目录未连接，标注只留在本次浏览"
  }
}

function onExport(): void {
  const payload = JSON.stringify({ type: "FeatureCollection", features: annotations.value })
  const url = URL.createObjectURL(new Blob([payload], { type: "application/geo+json" }))
  const link = document.createElement("a")
  link.href = url
  link.download = "annotations.geojson"
  link.click()
  URL.revokeObjectURL(url)
}

async function onCopy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(measureText.value)
    toolMessage.value = "已复制"
  } catch {
    toolMessage.value = "复制失败，请手动选择结果文字"
  }
}

function onFly(lon: number, lat: number): void {
  const error = coordinateError(lon, lat)
  if (error) {
    toolMessage.value = error
    return
  }
  handles?.flyTo(lon, lat)
  toolMessage.value = ""
}

function onSaveBookmark(name: string, lon: number, lat: number): void {
  const error = coordinateError(lon, lat)
  if (error) {
    toolMessage.value = error
    return
  }
  bookmarks.value = addBookmark(bookmarks.value, {
    name: name || `${lon},${lat}`,
    lon,
    lat,
    height: 1_500_000,
  })
  writeBookmarks(bookmarks.value)
}

function onUseBookmark(bookmark: Bookmark): void {
  flyLon.value = bookmark.lon
  flyLat.value = bookmark.lat
  handles?.flyTo(bookmark.lon, bookmark.lat, bookmark.height)
}

async function onLoadSource(payload: { id: string; name: string; datetime?: string; bbox?: number[] }): Promise<void> {
  const body: Record<string, unknown> = { limit: 1 }
  if (payload.datetime) body.datetime = payload.datetime
  if (payload.bbox) body.bbox = payload.bbox
  try {
    const response = await fetch(`/api/providers/${payload.id}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    const result = await response.json()
    if (!response.ok) {
      toolMessage.value = typeof result.detail === "string" ? result.detail : "加载失败"
      return
    }
    const items = result.items ?? []
    if (!items.length) {
      toolMessage.value = "没有可加载的图层"
      return
    }
    for (const item of items) {
      await placeLoadedItem(payload.id, payload.name, item)
    }
    toolMessage.value = `已加载 ${items.length} 条`
  } catch {
    toolMessage.value = "目录未连接"
  }
}

function layerName(item: { title: string; time?: string }): string {
  if (item.time && !item.title.includes(item.time)) return `${item.title} ${item.time}`
  return item.title
}

async function placeLoadedItem(
  sourceId: string,
  groupName: string,
  item: { id: string; title: string; time?: string; bbox?: number[]; layer: WireLayerSpec },
): Promise<void> {
  if (!handles) return
  const wire = item.layer
  const url = wire.url ?? ""
  const attribution = attributionOf(wire, item.title)
  let handle: LayerHandle
  // 后端声明了什么类型就用什么类型：xyz 是瓦片模板、wmts 读 capabilities 或
  // KVP 基地址、cog 是单幅影像。不再一律当 XYZ 模板套，那样 WMTS 是假挂载。
  const declaredType = wire.type
  if (declaredType === "wmts" && (wire.wmts_capabilities || wire.wmts_layer)) {
    handle = await handles.mountSwipeSide(toMountableLayer(wire, item.id), "none")
    if (!scenes.value.some((scene) => scene.id === item.id)) {
      scenes.value = [
        ...scenes.value,
        { id: item.id, source: sourceId === "arcgis_wayback" ? "wayback" : "stac", timeLabel: item.title, url, attribution },
      ]
    }
  } else if (url.includes("{z}") || url.includes("{TileMatrix}")) {
    handle = await handles.mountSwipeSide(toMountableLayer(wire, item.id), "none")
    if (!scenes.value.some((scene) => scene.id === item.id)) {
      scenes.value = [
        ...scenes.value,
        { id: item.id, source: sourceId === "arcgis_wayback" ? "wayback" : "stac", timeLabel: item.title, url, attribution },
      ]
    }
  } else if (item.bbox && item.bbox.length === 4 && /\.(png|jpe?g)(\?|$)/i.test(url)) {
    const [west, south, east, north] = item.bbox
    handle = await handles.mountLocatedImage(url, west, south, east, north)
  } else {
    toolMessage.value = `${item.title} 已写入目录。该结果不是可直接铺到地球的瓦片。`
    return
  }
  extraLayers.set(item.id, handle)
  managedLayers.value = [
    ...managedLayers.value,
    { id: item.id, name: layerName(item), group: groupName, visible: true, opacity: 1, order: 300 + managedLayers.value.length },
  ]
}

async function onCustomXyz(template: {
  name: string
  url_template: string
  tiling_scheme: string
  max_zoom: number
  layer_kind: string
  time: string
}): Promise<void> {
  try {
    const response = await fetch("/api/providers/custom_xyz/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template }),
    })
    const body = await response.json()
    if (!response.ok) {
      toolMessage.value = typeof body.detail === "string" ? body.detail : "添加失败"
      return
    }
    const item = body.items?.[0]
    if (!item || !handles) return
    const handle = await handles.mountSwipeSide(
      {
        ...toMountableLayer(item.layer, item.id),
        // 自定义地址的授权由用户自己负责，署名不该由平台代填。
        attribution: "用户自备地址",
      },
      "none",
    )
    extraLayers.set(item.id, handle)
    managedLayers.value = [
      ...managedLayers.value,
      {
        id: item.id,
        name: item.title,
        group: "自定义 XYZ",
        visible: true,
        opacity: 1,
        order: 200 + managedLayers.value.length,
      },
    ]
    toolMessage.value = `已添加 ${item.title}`
  } catch {
    toolMessage.value = "目录未连接，自定义地址未添加"
  }
}

async function loadSources(): Promise<void> {
  try {
    const response = await fetch("/api/providers")
    if (!response.ok) return
    const rows = await response.json()
    sources.value = rows
      .filter((row: { id: string }) => !row.id.startsWith("sample_"))
      .map((row: { id: string; name: string; availability?: string; drape?: boolean; picker?: "time" | "extent" | "template" | null }) => ({
        id: row.id,
        name: row.name,
        availability: row.availability ?? "ready",
        drape: Boolean(row.drape),
        picker: row.picker ?? null,
      }))
  } catch {
    sources.value = []
  }
}

async function loadAnnotations(): Promise<void> {
  try {
    const response = await fetch("/api/annotations")
    if (!response.ok) return
    const body = await response.json()
    const features: unknown[] = Array.isArray(body?.features) ? body.features : []
    const loaded: { id?: string; geometry: GeoGeometry }[] = []
    for (const feature of features) {
      const geometry = asGeoGeometry((feature as { geometry?: unknown }).geometry)
      if (!geometry) continue
      const id = (feature as { id?: unknown }).id
      loaded.push({ id: id === undefined ? undefined : String(id), geometry })
      handles?.showAnnotation(String(id), geometry)
    }
    annotations.value = loaded
  } catch {
    toolMessage.value = ""
  }
}

function startDrag(event: PointerEvent): void {
  const bounds = document.getElementById("cesium")?.getBoundingClientRect()
  if (!bounds || !handles) return
  const move = (pointer: PointerEvent) => {
    split.value = splitFromPointer(pointer.clientX, bounds.left, bounds.width)
    handles?.setSplitPosition(split.value)
  }
  const stop = () => {
    window.removeEventListener("pointermove", move)
    window.removeEventListener("pointerup", stop)
  }
  window.addEventListener("pointermove", move)
  window.addEventListener("pointerup", stop)
  move(event)
}
</script>

<template>
  <div class="shell">
    <div id="cesium"></div>
    <p v-if="errorText" class="error">{{ attribution }}</p>
    <div
      v-show="swipeOn"
      class="divider"
      role="slider"
      aria-label="分隔条"
      :style="{ left: `${split * 100}%` }"
      @pointerdown="startDrag"
    ></div>
    <ToolsPanel
      v-model:imagery-on="imageryOn"
      v-model:terrain-on="terrainOn"
      v-model:tileset-on="tilesetOn"
      v-model:opacity="opacity"
      v-model:screen-error="screenError"
      v-model:swipe-on="swipeOn"
      v-model:left-id="leftId"
      v-model:right-id="rightId"
      v-model:lon="flyLon"
      v-model:lat="flyLat"
      v-model:bookmark-name="bookmarkName"
      :scenes="scenes"
      :tileset-configured="tilesetConfigured"
      :layers="managedLayers"
      :message="toolMessage"
      :sketching="sketching"
      :measure-text="measureText"
      :bookmarks="bookmarks"
      :sources="sources"
      v-model:xyz-name="xyzName"
      v-model:xyz-url="xyzUrl"
      v-model:xyz-scheme="xyzScheme"
      v-model:xyz-kind="xyzKind"
      v-model:xyz-zoom="xyzZoom"
      v-model:xyz-time="xyzTime"
      @custom-xyz="onCustomXyz"
      @load-source="onLoadSource"
      @visible="onLayerVisible"
      @opacity="onLayerOpacity"
      @move="onLayerMove"
      @remove="onLayerRemove"
      @sketch="onSketch"
      @finish="onFinish"
      @export-geojson="onExport"
      @copy="onCopy"
      @home="handles?.flyHome()"
      @fly="onFly"
      @fly-extent="handles?.flyToExtent()"
      @save-bookmark="onSaveBookmark"
      @use-bookmark="onUseBookmark"
    />
    <p v-if="attribution" class="credit">{{ attribution }}</p>
  </div>
</template>

<style>
html,
body,
#app,
.shell,
#cesium {
  margin: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.cesium-viewer-bottom,
.cesium-widget-credits {
  display: none !important;
}
.credit {
  position: absolute;
  right: 12px;
  bottom: 8px;
  z-index: 2;
  margin: 0;
  color: rgba(255, 255, 255, 0.72);
  font: 11px/1.3 "Segoe UI", sans-serif;
}
.error {
  position: absolute;
  top: 16px;
  left: 332px;
  z-index: 2;
  margin: 0;
  color: #ffb4b4;
}
.divider {
  position: absolute;
  top: 0;
  z-index: 3;
  width: 4px;
  height: 100%;
  margin-left: -2px;
  background: #fff;
  cursor: ew-resize;
  touch-action: none;
}
</style>
