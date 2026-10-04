<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue"
import { attributionOf, toMountableLayer, type WireLayerSpec } from "./api/layerSpec"
import {
  cancelJob,
  deleteAnnotation,
  layerSpec,
  listAnnotations,
  listJobs,
  listProviders,
  readJob,
  saveAnnotation,
  searchProvider,
  tileTiming,
  uploadCog,
  type CatalogSource,
  type Job,
} from "./api/client"
import { pollJob } from "./api/jobs"
import { resolveGlobeConfig } from "./config"
import { configureCesium } from "./map/cesiumLayers"
import { asGeoGeometry, startGlobe, type GeoGeometry, type GlobeHandles } from "./map/globe"
import { isSketchKind, type SketchKind } from "./map/sketchKind"
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
const annotations = ref<AnnotationRow[]>([])
const sources = ref<CatalogSource[]>([])
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

/**
 * `saved` 区分这条标注是不是真的写进了目录。
 *
 * 目录未连接时 `saveAnnotation` 会失败，此时标注只留在本次浏览，id 是本地
 * `crypto.randomUUID()`。拿这个 id 去 `DELETE /annotations/{id}` 只会得到 404，
 * 所以擦除时必须知道哪些能真的删。
 */
interface AnnotationRow {
  id?: string
  geometry: GeoGeometry
  saved: boolean
}
let handles: GlobeHandles | null = null
let swipeLeft: LayerHandle | null = null
let swipeRight: LayerHandle | null = null
const jobs = ref<Job[]>([])
// 同一时刻只跟一个任务。新一轮上传会中止上一轮，避免两个轮询同时刷状态。
let jobPoll: AbortController | null = null

onUnmounted(() => {
  jobPoll?.abort()
  jobPoll = null
})

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
    await loadJobs()
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
    // 顺手把分隔条归位。不重置的话下次打开卷帘，分隔条会停在上次拖到的位置，
    // 看着像是没生效。
    handles.setSplitPosition(0)
    split.value = 0.5
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

function onSketch(kind: SketchKind): void {
  // emit 的类型已经是联合类型，按钮里拼错会被 vue-tsc 拦下；这里再收一次是
  // 运行时兜底。之前那句 `handles?.beginSketch(kind as "point")` 把整个联合按成了
  // "point"，等于编译器彻底不管这件事。
  if (!isSketchKind(kind)) return
  sketching.value = true
  toolMessage.value = ""
  handles?.beginSketch(kind)
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
    const feature = await saveAnnotation(result.geometry)
    annotations.value = [...annotations.value, { id: feature.id ?? localId, geometry: result.geometry, saved: true }]
    toolMessage.value = "已写入目录"
  } catch {
    annotations.value = [...annotations.value, { id: localId, geometry: result.geometry, saved: false }]
    toolMessage.value = "目录未连接，标注只留在本次浏览"
  }
}

/**
 * 擦掉最近一条标注。地球上的实体总是能擦；只有真写进目录的才去发 DELETE。
 * 后端删不掉时要说清楚库里还留着，否则刷新一下标注又回来了，会被当成没生效。
 */
async function onEraseLastAnnotation(): Promise<void> {
  const last = annotations.value[annotations.value.length - 1]
  if (!last?.id) {
    toolMessage.value = "没有可擦除的标注"
    return
  }
  handles?.eraseAnnotation(last.id)
  annotations.value = annotations.value.slice(0, -1)
  if (!last.saved) {
    toolMessage.value = "已擦除最近一条标注"
    return
  }
  try {
    await deleteAnnotation(last.id)
    toolMessage.value = "已擦除最近一条标注"
  } catch {
    toolMessage.value = "已从地球上擦除，但目录未连接，库里仍留着这一条"
  }
}

/** 清除全部标注。地球与目录一起清，目录不可用时如实说明剩下什么。 */
async function onClearAnnotations(): Promise<void> {
  const removed = annotations.value
  if (!removed.length) {
    toolMessage.value = "没有可清除的标注"
    return
  }
  handles?.clearAnnotations()
  annotations.value = []
  const persisted = removed.filter((row) => row.saved && row.id).map((row) => row.id as string)
  if (!persisted.length) {
    toolMessage.value = `已清除 ${removed.length} 条标注`
    return
  }
  try {
    await Promise.all(persisted.map((id) => deleteAnnotation(id)))
    toolMessage.value = `已清除 ${removed.length} 条标注`
  } catch {
    toolMessage.value = `已从地球上清除 ${removed.length} 条，但目录未连接，库里仍留着`
  }
}

/** 量算没有入库这回事，所以只清地球上的草稿与结果文字。 */
function onClearMeasure(): void {
  handles?.clearSketch()
  measureText.value = ""
  sketching.value = false
  toolMessage.value = "已清除量算"
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
  const body: { limit: number; datetime?: string; bbox?: number[] } = { limit: 1 }
  if (payload.datetime) body.datetime = payload.datetime
  if (payload.bbox) body.bbox = payload.bbox
  try {
    const items = await searchProvider(payload.id, body)
    if (!items.length) {
      toolMessage.value = "没有可加载的图层"
      return
    }
    for (const item of items) {
      await placeLoadedItem(payload.id, payload.name, item)
    }
    toolMessage.value = `已加载 ${items.length} 条`
  } catch (error) {
    toolMessage.value = error instanceof Error ? error.message : "目录未连接"
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
    const items = await searchProvider("custom_xyz", { template })
    const item = items[0]
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
    // 演示用的 sample_* 不该出现在给用户看的弹层里
    sources.value = (await listProviders()).filter((row) => !row.id.startsWith("sample_"))
  } catch {
    sources.value = []
  }
}

async function loadAnnotations(): Promise<void> {
  try {
    const features = await listAnnotations()
    const loaded: AnnotationRow[] = []
    for (const feature of features) {
      const geometry = asGeoGeometry(feature.geometry)
      if (!geometry) continue
      loaded.push({ id: feature.id, geometry, saved: true })
      if (feature.id) handles?.showAnnotation(feature.id, geometry)
    }
    annotations.value = loaded
  } catch {
    toolMessage.value = ""
  }
}

async function loadJobs(): Promise<void> {
  try {
    jobs.value = await listJobs({ limit: 12 })
  } catch {
    // 任务列表不是主链路，拉不到就静默，保持上一次的结果
  }
}

async function onUploadCog(payload: { file: File; acquiredAt: string }): Promise<void> {
  toolMessage.value = "正在上传…"
  try {
    const queued = await uploadCog(payload.file, `${payload.acquiredAt}T00:00:00Z`)
    upsertJob(queued)
    toolMessage.value = "已入队，正在转 COG"
    await loadJobs()
    // COG 转换是分钟级的，所以放到后台轮询；用户可以继续操作别的图层。
    void watchJob(queued.id)
  } catch (error) {
    toolMessage.value = error instanceof Error ? error.message : "上传失败"
  }
}

async function watchJob(jobId: string): Promise<void> {
  if (jobPoll) jobPoll.abort()
  jobPoll = new AbortController()
  try {
    const finished = await pollJob(jobId, readJob, {
      signal: jobPoll.signal,
      onUpdate: upsertJob,
    })
    if (finished.status === "success") {
      await mountIngested(finished.payload.item_id ?? finished.id)
    } else if (finished.status === "failed") {
      toolMessage.value = finished.error ? `入库失败：${finished.error}` : "入库失败"
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return
    toolMessage.value = error instanceof Error ? error.message : "入库状态未知"
  } finally {
    jobPoll = null
  }
}

function upsertJob(job: Job): void {
  const rest = jobs.value.filter((row) => row.id !== job.id)
  jobs.value = [job, ...rest].slice(0, 12)
}

/** 入库完成后把图层挂到地球上——这样"上传"才有看得见的产出。 */
async function mountIngested(itemId: string): Promise<void> {
  try {
    const wire = await layerSpec(itemId)
    if (!handles) return
    const handle = await handles.mountSwipeSide(
      toMountableLayer(wire, itemId),
      "none",
    )
    extraLayers.set(itemId, handle)
    managedLayers.value = [
      ...managedLayers.value,
      {
        id: itemId,
        name: `上传 ${itemId.slice(0, 8)}`,
        group: "本地入库",
        visible: true,
        opacity: 1,
        order: 100 + managedLayers.value.length,
      },
    ]
    toolMessage.value = "入库完成，图层已挂上地球"
  } catch (error) {
    toolMessage.value = error instanceof Error ? error.message : "取图层描述失败"
  }
}

async function onCancelJob(jobId: string): Promise<void> {
  try {
    upsertJob(await cancelJob(jobId))
  } catch (error) {
    toolMessage.value = error instanceof Error ? error.message : "取消失败"
  }
}

async function onSampleTiming(): Promise<void> {
  const layer = managedLayers.value.find((row) => row.group === "本地入库")
  if (!layer) {
    toolMessage.value = "先上传一景影像，才能采样切片耗时"
    return
  }
  try {
    const wire = await layerSpec(layer.id)
    if (!wire.url) {
      toolMessage.value = "该图层没有可采样的瓦片地址"
      return
    }
    const href = new URL(wire.url, window.location.href)
    const target = href.searchParams.get("url") ?? ""
    const timing = await tileTiming({ url: target, z: 0, x: 0, y: 0 })
    toolMessage.value = timing.sampled
      ? `切片耗时 ${timing.duration_ms} ms（缓存：${timing.cache}）`
      : timing.note
  } catch (error) {
    toolMessage.value = error instanceof Error ? error.message : "采样失败"
  }
}

function startDrag(event: PointerEvent): void {
  const bounds = document.getElementById("cesium")?.getBoundingClientRect()
  if (!bounds || !handles) return
  const move = (pointer: PointerEvent) => {
    split.value = splitFromPointer(pointer.clientX, bounds.left, bounds.width)
    handles?.setSplitPosition(split.value)
  }
  // pointercancel 与 blur 也要解绑：否则在指针捕获丢失（切标签页、系统弹窗、
  // 触控被系统接管）时 move/stop 会一直挂着，下一次拖拽解绑的是新一组监听，
  // 旧的泄漏掉。stop 里的 removeEventListener 是幂等的，多解一次无害。
  const stop = () => {
    window.removeEventListener("pointermove", move)
    window.removeEventListener("pointerup", stop)
    window.removeEventListener("pointercancel", stop)
    window.removeEventListener("blur", stop)
  }
  window.addEventListener("pointermove", move)
  window.addEventListener("pointerup", stop)
  window.addEventListener("pointercancel", stop)
  window.addEventListener("blur", stop)
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
      :annotation-count="annotations.length"
      :bookmarks="bookmarks"
      :sources="sources"
      :jobs="jobs"
      v-model:xyz-name="xyzName"
      v-model:xyz-url="xyzUrl"
      v-model:xyz-scheme="xyzScheme"
      v-model:xyz-kind="xyzKind"
      v-model:xyz-zoom="xyzZoom"
      v-model:xyz-time="xyzTime"
      @custom-xyz="onCustomXyz"
      @load-source="onLoadSource"
      @upload-cog="onUploadCog"
      @refresh-jobs="loadJobs"
      @cancel-job="onCancelJob"
      @sample-timing="onSampleTiming"
      @visible="onLayerVisible"
      @opacity="onLayerOpacity"
      @move="onLayerMove"
      @remove="onLayerRemove"
      @sketch="onSketch"
      @finish="onFinish"
      @erase-last-annotation="onEraseLastAnnotation"
      @clear-annotations="onClearAnnotations"
      @clear-measure="onClearMeasure"
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
