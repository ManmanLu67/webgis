import * as Cesium from "cesium"
import type { ResolvedGlobe } from "../config"
import "./cesiumLayers"
import { clampOpacity, createLayer, type LayerHandle, type LayerSpec, type SplitSide } from "./layerTypeRegistry"
import { formatMeasure, heightMeters, pathDistance, ringArea, type LonLat } from "./measure"
import type { SketchKind } from "./sketchKind"

export type { SketchKind } from "./sketchKind"

export interface GlobeHandles {
  imagery: LayerHandle
  terrain: LayerHandle
  tileset: LayerHandle | null
  setSplitPosition(position: number): void
  mountSwipeSide(spec: LayerSpec, side: SplitSide): Promise<LayerHandle>
  mountLocatedImage(url: string, west: number, south: number, east: number, north: number): Promise<LayerHandle>
  beginSketch(kind: SketchKind): void
  finishSketch(): SketchResult | null
  showAnnotation(id: string, geometry: GeoGeometry): void
  /** 擦掉一条已完成的标注（地球上的实体）。 */
  eraseAnnotation(id: string): void
  /** 擦掉全部已完成的标注。 */
  clearAnnotations(): void
  /** 放弃当前正在画的草稿，不留下任何实体。 */
  clearSketch(): void
  flyTo(lon: number, lat: number, height?: number): void
  /** 有范围就飞到那一块；没有则飞到当前视野，视野不着地时退回全球。 */
  flyToExtent(extent?: { west: number; south: number; east: number; north: number }): void
  flyHome(): void
  /** 关掉地球、事件和帧率监听。组件卸载时调用，否则 WebGL 上下文留着。 */
  destroy(): void
}

function unloaded(): DOMException {
  return new DOMException("地球已卸载", "AbortError")
}

function throwIfUnloaded(signal?: AbortSignal): void {
  if (signal?.aborted) throw unloaded()
}

/** 容器一开始是 0 高时，渲染循环会跳过绘制且不报错。尺寸回来后再 resize 一次。 */
function watchContainerSize(viewer: Cesium.Viewer, container: HTMLElement): () => void {
  let width = container.clientWidth
  let height = container.clientHeight
  const observer = new ResizeObserver(() => {
    if (viewer.isDestroyed()) return
    const nextWidth = container.clientWidth
    const nextHeight = container.clientHeight
    if (nextWidth === width && nextHeight === height) return
    width = nextWidth
    height = nextHeight
    viewer.resize()
  })
  observer.observe(container)
  return () => observer.disconnect()
}

export async function startGlobe(
  container: HTMLElement,
  config: ResolvedGlobe,
  signal?: AbortSignal,
): Promise<GlobeHandles> {
  throwIfUnloaded(signal)
  const viewer = new Cesium.Viewer(container, {
    animation: false,
    timeline: false,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    fullscreenButton: false,
    baseLayer: false,
    infoBox: false,
    selectionIndicator: false,
  })
  const stopSizeWatch = watchContainerSize(viewer, container)
  let sketch: ReturnType<typeof attachSketch> | null = null
  let stopFrameRate: (() => void) | null = null
  let closed = false
  let onAbort = (): void => {}
  const teardown = (): void => {
    if (closed) return
    closed = true
    signal?.removeEventListener("abort", onAbort)
    stopSizeWatch()
    sketch?.dispose()
    stopFrameRate?.()
    if (!viewer.isDestroyed()) viewer.destroy()
  }
  onAbort = () => teardown()
  signal?.addEventListener("abort", onAbort)
  const homeDestination = viewer.camera.positionWC.clone()
  const homeDirection = viewer.camera.directionWC.clone()
  const homeUp = viewer.camera.upWC.clone()
  // 极点露出的底色。Web Mercator 在数学上就到 ±85.0511°
  // （WebMercatorProjection.MaximumLatitude），那以外没有任何瓦片网格可铺，
  // 于是露出 Globe 的默认底色 —— 那是 rgb(0,0,0.5) 的深蓝，在深色面板上很扎眼。
  // 换成接近极地冰雪的浅色。OSM、Esri 这类只能到 85° 的源仍然走这条兜底；
  // 能铺到 ±90 的 Geographic 源则不会露出这块底色。
  try {
  throwIfUnloaded(signal)
  viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#eaf1f7")
  const imagery = await createLayer(config.imagery).attach(viewer)
  throwIfUnloaded(signal)
  const terrain = await createLayer(config.terrain).attach(viewer)
  throwIfUnloaded(signal)
  const tileset = config.tileset.url ? await createLayer(config.tileset).attach(viewer) : null
  throwIfUnloaded(signal)
  const liveSketch = attachSketch(viewer)
  sketch = liveSketch
  const stopRate = watchFrameRate(viewer)
  stopFrameRate = stopRate
  viewer.resize()
  return {
    imagery,
    terrain,
    tileset,
    setSplitPosition(position: number) {
      if (viewer.isDestroyed()) return
      viewer.scene.splitPosition = position
    },
    async mountSwipeSide(spec: LayerSpec, side: SplitSide) {
      if (viewer.isDestroyed()) throw unloaded()
      const handle = await createLayer(spec).attach(viewer)
      if (viewer.isDestroyed()) {
        try {
          handle.remove()
        } catch {
          // 球已经拆掉时，这一层也跟着没了。
        }
        throw unloaded()
      }
      handle.setSplit(side)
      return handle
    },
    async mountLocatedImage(url, west, south, east, north) {
      if (viewer.isDestroyed()) throw unloaded()
      const provider = await Cesium.SingleTileImageryProvider.fromUrl(url, {
        rectangle: Cesium.Rectangle.fromDegrees(west, south, east, north),
      })
      if (viewer.isDestroyed()) throw unloaded()
      const layer = viewer.imageryLayers.addImageryProvider(provider)
      return {
        attribution: "",
        setShow(show: boolean) {
          layer.show = show
        },
        setOpacity(value: number) {
          layer.alpha = clampOpacity(value)
        },
        setMaximumScreenSpaceError() {},
        setSplit() {},
        raise() {
          viewer.imageryLayers.raise(layer)
        },
        lower() {
          viewer.imageryLayers.lower(layer)
        },
        remove() {
          viewer.imageryLayers.remove(layer, true)
        },
      }
    },
    beginSketch(kind) {
      if (viewer.isDestroyed()) return
      liveSketch.begin(kind)
    },
    finishSketch() {
      if (viewer.isDestroyed()) return null
      return liveSketch.finish()
    },
    showAnnotation(id, geometry) {
      if (viewer.isDestroyed()) return
      liveSketch.show(id, geometry)
    },
    eraseAnnotation(id) {
      if (viewer.isDestroyed()) return
      liveSketch.erase(id)
    },
    clearAnnotations() {
      if (viewer.isDestroyed()) return
      liveSketch.eraseAll()
    },
    clearSketch() {
      if (viewer.isDestroyed()) return
      liveSketch.clearDraft()
    },
    flyTo(lon, lat, height = 1_500_000) {
      if (viewer.isDestroyed()) return
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, height),
        duration: 1.2,
      })
    },
    flyToExtent(extent) {
      if (viewer.isDestroyed()) return
      // 点的是某一条图层时飞到它自己的范围。没有范围（底图、地形）才退回
      // 当前视野；看不到地面时再退回全球。以前这个按钮不看图层，对着一景
      // 局部影像也会飞到相机正看着的那一块。
      const destination = extent
        ? Cesium.Rectangle.fromDegrees(extent.west, extent.south, extent.east, extent.north)
        : viewer.camera.computeViewRectangle(viewer.scene.globe.ellipsoid, globeRectangleScratch) ??
          defaultWorldRectangle(globeRectangleScratch)
      viewer.camera.flyTo({ destination, duration: 1.2 })
    },
    flyHome() {
      if (viewer.isDestroyed()) return
      viewer.camera.cancelFlight()
      viewer.camera.flyTo({
        destination: homeDestination,
        orientation: { direction: homeDirection, up: homeUp },
        duration: 1.2,
      })
    },
    destroy() {
      teardown()
    },
  }
  } catch (error) {
    teardown()
    if (signal?.aborted) throw unloaded()
    throw error
  }
}

/** Cesium 的 Rectangle 是可变对象，复用同一个避免每次分配。 */
const globeRectangleScratch = new Cesium.Rectangle()

function defaultWorldRectangle(scratch: Cesium.Rectangle): Cesium.Rectangle {
  return Cesium.Rectangle.fromDegrees(-160, -70, 160, 70, scratch)
}

/**
 * 可辨识联合：按 `type` 就能收窄出对应的坐标层级。
 * 之前写成一个带联合坐标的接口，结果处处要 `as number[][]`，
 * 编译器也没法在拼实体的时候替你把关。
 */
export type GeoGeometry =
  | { type: "Point"; coordinates: number[] }
  | { type: "LineString"; coordinates: number[][] }
  | { type: "Polygon"; coordinates: number[][][] }

const GEOMETRY_TYPES: ReadonlySet<string> = new Set(["Point", "LineString", "Polygon"])

/**
 * 接口回来的 JSON 是 `any`，直接喂给 `showAnnotation` 会把没验证过的数据
 * 当成合法几何。这里按后端 `app/annotations.py` 的同一套规则收窄——
 * 点至少两个坐标、线至少两个点、面至少四个位置。
 */
export function asGeoGeometry(value: unknown): GeoGeometry | null {
  if (typeof value !== "object" || value === null) return null
  const candidate = value as { type?: unknown; coordinates?: unknown }
  if (typeof candidate.type !== "string" || !GEOMETRY_TYPES.has(candidate.type)) return null
  if (!Array.isArray(candidate.coordinates)) return null
  const minimum = candidate.type === "Point" ? 2 : candidate.type === "LineString" ? 2 : 4
  if (candidate.coordinates.length < minimum) return null
  if (candidate.type === "Point") {
    return { type: "Point", coordinates: candidate.coordinates as number[] }
  }
  if (candidate.type === "LineString") {
    return { type: "LineString", coordinates: candidate.coordinates as number[][] }
  }
  return { type: "Polygon", coordinates: candidate.coordinates as number[][][] }
}

export interface SketchResult {
  geometry: GeoGeometry | null
  text: string | null
  message: string | null
}

function attachSketch(viewer: Cesium.Viewer) {
  const points: Cesium.Cartesian3[] = []
  let kind: SketchKind | null = null
  let draft: Cesium.Entity | null = null
  // 已完成标注的实体 id。分开记是因为草稿不该被"清除标注"顺手带走，
  // 而擦标注也不该动正在画的线——两者的生命周期不同。
  const annotations = new Set<string>()
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
  handler.setInputAction((click: { position: Cesium.Cartesian2 }) => {
    if (!kind) return
    const cartesian = viewer.camera.pickEllipsoid(click.position, viewer.scene.globe.ellipsoid)
    if (!cartesian) return
    points.push(cartesian)
    paint()
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK)

  function paint(): void {
    if (draft) viewer.entities.remove(draft)
    if (points.length === 0) {
      draft = null
      return
    }
    draft = viewer.entities.add({
      position: points.length === 1 ? points[0] : undefined,
      point: points.length === 1 ? { pixelSize: 10, color: Cesium.Color.YELLOW } : undefined,
      polyline:
        points.length > 1
          ? { positions: [...points], width: 2, material: Cesium.Color.YELLOW }
          : undefined,
    })
  }

  function asLonLat(cartesian: Cesium.Cartesian3): LonLat {
    const cartographic = Cesium.Cartographic.fromCartesian(cartesian)
    return {
      lon: Cesium.Math.toDegrees(cartographic.longitude),
      lat: Cesium.Math.toDegrees(cartographic.latitude),
      height: cartographic.height,
    }
  }

  return {
    begin(next: SketchKind) {
      kind = next
      points.length = 0
      paint()
    },
    finish(): SketchResult | null {
      const samples = points.map(asLonLat)
      if (kind === "distance" || kind === "area" || kind === "height") {
        if (kind === "height" && samples.length < 2) return { geometry: null, text: null, message: "高度需要两个点" }
        if (kind === "distance" && samples.length < 2) return { geometry: null, text: null, message: "距离至少两个点" }
        if (kind === "area" && samples.length < 3) return { geometry: null, text: null, message: "面积至少三个点" }
        const active = kind
        const value =
          active === "distance"
            ? pathDistance(samples)
            : active === "area"
              ? ringArea(samples)
              : heightMeters(samples[0].height ?? 0, samples[samples.length - 1].height ?? 0)
        kind = null
        const measureKind = active === "height" ? "height" : active === "area" ? "area" : "distance"
        return { geometry: null, text: formatMeasure(measureKind, value), message: null }
      }
      const geometry = geometryOf(kind, samples)
      if (!geometry) return { geometry: null, text: null, message: "点数不够" }
      kind = null
      return { geometry, text: null, message: null }
    },
    show(id: string, geometry: GeoGeometry) {
      const existing = viewer.entities.getById(id)
      if (existing) viewer.entities.remove(existing)
      viewer.entities.add(entityFromGeometry(id, geometry))
      annotations.add(id)
    },
    erase(id: string) {
      const existing = viewer.entities.getById(id)
      if (existing) viewer.entities.remove(existing)
      annotations.delete(id)
    },
    eraseAll() {
      for (const id of annotations) {
        const existing = viewer.entities.getById(id)
        if (existing) viewer.entities.remove(existing)
      }
      annotations.clear()
    },
    clearDraft() {
      kind = null
      points.length = 0
      if (draft) viewer.entities.remove(draft)
      draft = null
    },
    dispose() {
      if (!handler.isDestroyed()) handler.destroy()
    },
  }
}

function geometryOf(kind: SketchKind | null, samples: LonLat[]): GeoGeometry | null {
  if (kind === "point" && samples.length >= 1) {
    return { type: "Point", coordinates: [samples[0].lon, samples[0].lat, samples[0].height ?? 0] }
  }
  if (kind === "line" && samples.length >= 2) {
    return { type: "LineString", coordinates: samples.map((sample) => [sample.lon, sample.lat, sample.height ?? 0]) }
  }
  if (kind === "polygon" && samples.length >= 3) {
    const ring = samples.map((sample) => [sample.lon, sample.lat, sample.height ?? 0])
    ring.push(ring[0])
    return { type: "Polygon", coordinates: [ring] }
  }
  return null
}

function entityFromGeometry(id: string, geometry: GeoGeometry): Cesium.Entity.ConstructorOptions {
  if (geometry.type === "Point") {
    const [lon, lat, height] = geometry.coordinates
    return {
      id,
      position: Cesium.Cartesian3.fromDegrees(lon, lat, height ?? 0),
      point: { pixelSize: 10, color: Cesium.Color.CYAN },
    }
  }
  if (geometry.type === "LineString") {
    return {
      id,
      polyline: {
        positions: Cesium.Cartesian3.fromDegreesArrayHeights(geometry.coordinates.flat()),
        width: 2,
        material: Cesium.Color.CYAN,
      },
    }
  }
  const ring = geometry.coordinates[0]
  return {
    id,
    polygon: {
      hierarchy: Cesium.Cartesian3.fromDegreesArrayHeights(ring.flat()),
      material: Cesium.Color.CYAN.withAlpha(0.35),
    },
  }
}

function watchFrameRate(viewer: Cesium.Viewer): () => void {
  let frames = 0
  let windowStart = performance.now()
  const tick = (): void => {
    frames += 1
    const now = performance.now()
    if (now - windowStart < 1000) return
    const fps = Math.round((frames * 1000) / (now - windowStart))
    const node = document.getElementById("fps")
    if (node) node.textContent = String(fps)
    frames = 0
    windowStart = now
  }
  viewer.scene.postRender.addEventListener(tick)
  return () => {
    if (!viewer.isDestroyed()) viewer.scene.postRender.removeEventListener(tick)
  }
}
