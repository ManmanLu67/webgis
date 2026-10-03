import * as Cesium from "cesium"
import type { ResolvedGlobe } from "../config"
import "./cesiumLayers"
import { createLayer, type LayerHandle, type LayerSpec, type SplitSide } from "./layerTypeRegistry"
import { formatMeasure, heightMeters, pathDistance, ringArea, type LonLat } from "./measure"

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
  flyTo(lon: number, lat: number, height?: number): void
  flyToExtent(): void
  flyHome(): void
}

export async function startGlobe(container: HTMLElement, config: ResolvedGlobe): Promise<GlobeHandles> {
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
  const homeDestination = viewer.camera.positionWC.clone()
  const homeDirection = viewer.camera.directionWC.clone()
  const homeUp = viewer.camera.upWC.clone()
  const imagery = await createLayer(config.imagery).attach(viewer)
  const terrain = await createLayer(config.terrain).attach(viewer)
  const tileset = config.tileset.url ? await createLayer(config.tileset).attach(viewer) : null
  const sketch = attachSketch(viewer)
  watchFrameRate(viewer)
  return {
    imagery,
    terrain,
    tileset,
    setSplitPosition(position: number) {
      viewer.scene.splitPosition = position
    },
    async mountSwipeSide(spec: LayerSpec, side: SplitSide) {
      const handle = await createLayer(spec).attach(viewer)
      handle.setSplit(side)
      return handle
    },
    async mountLocatedImage(url, west, south, east, north) {
      const provider = await Cesium.SingleTileImageryProvider.fromUrl(url, {
        rectangle: Cesium.Rectangle.fromDegrees(west, south, east, north),
      })
      const layer = viewer.imageryLayers.addImageryProvider(provider)
      return {
        attribution: "",
        setShow(show: boolean) {
          layer.show = show
        },
        setOpacity(value: number) {
          layer.alpha = value
        },
        setMaximumScreenSpaceError() {},
        setSplit() {},
        remove() {
          viewer.imageryLayers.remove(layer, true)
        },
      }
    },
    beginSketch(kind) {
      sketch.begin(kind)
    },
    finishSketch() {
      return sketch.finish()
    },
    showAnnotation(id, geometry) {
      sketch.show(id, geometry)
    },
    flyTo(lon, lat, height = 1_500_000) {
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, height),
        duration: 1.2,
      })
    },
    flyToExtent() {
      viewer.camera.flyTo({
        destination: Cesium.Rectangle.fromDegrees(-160, -70, 160, 70),
        duration: 1.2,
      })
    },
    flyHome() {
      viewer.camera.cancelFlight()
      viewer.camera.flyTo({
        destination: homeDestination,
        orientation: { direction: homeDirection, up: homeUp },
        duration: 1.2,
      })
    },
  }
}

export type SketchKind = "point" | "line" | "polygon" | "distance" | "area" | "height"

export interface GeoGeometry {
  type: "Point" | "LineString" | "Polygon"
  coordinates: number[] | number[][] | number[][][]
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
    const [lon, lat, height] = geometry.coordinates as number[]
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
        positions: Cesium.Cartesian3.fromDegreesArrayHeights((geometry.coordinates as number[][]).flat()),
        width: 2,
        material: Cesium.Color.CYAN,
      },
    }
  }
  const ring = (geometry.coordinates as number[][][])[0]
  return {
    id,
    polygon: {
      hierarchy: Cesium.Cartesian3.fromDegreesArrayHeights(ring.flat()),
      material: Cesium.Color.CYAN.withAlpha(0.35),
    },
  }
}

function watchFrameRate(viewer: Cesium.Viewer): void {
  let frames = 0
  let windowStart = performance.now()
  viewer.scene.postRender.addEventListener(() => {
    frames += 1
    const now = performance.now()
    if (now - windowStart < 1000) return
    const fps = Math.round((frames * 1000) / (now - windowStart))
    const node = document.getElementById("fps")
    if (node) node.textContent = String(fps)
    frames = 0
    windowStart = now
  })
}
