import { LAYER_TYPES, type LayerSpec, type LayerType } from "../map/layerTypeRegistry"

/**
 * 后端 `LayerSpec` 的线上形状。字段名是 snake_case，前端用的是 camelCase，
 * 转换只在这一处发生，别处不再各写一份内联结构。
 */
export interface WireLayerSpec {
  id?: string
  type?: string
  url?: string
  time_dimension?: string | null
  publisher_id?: string
  url_template?: string | null
  tiling_scheme?: string
  max_zoom?: number | null
  layer_kind?: string
  crs?: string
  attribution?: string
  license_note?: string
  wmts_capabilities?: string | null
  wmts_layer?: string | null
  wmts_tile_template?: string | null
  wmts_style?: string
  wmts_tile_matrix_set_id?: string
  wmts_format?: string
  wmts_dimensions?: Record<string, string> | null
  georeference_note?: string
  variants?: string[]
}

function asLayerType(value: unknown): LayerType | null {
  return LAYER_TYPES.includes(value as LayerType) ? (value as LayerType) : null
}

function asTilingScheme(value: unknown): "WebMercator" | "Geographic" | undefined {
  return value === "Geographic" || value === "WebMercator" ? value : undefined
}

function asStringMap(value: unknown): Record<string, string> | undefined {
  if (typeof value !== "object" || value === null) return undefined
  const entries = Object.entries(value as Record<string, unknown>).filter((pair): pair is [string, string] =>
    typeof pair[1] === "string",
  )
  return entries.length ? Object.fromEntries(entries) : undefined
}

/**
 * 线上图层描述 → 前端可加载的图层描述。
 *
 * 后端声明了什么类型就用什么类型，不再一律当 XYZ 模板套。这样 `wmts` 才真的是
 * WMTS（读 capabilities / KVP 基地址），`cog` 才真的是单幅影像。
 * 类型不认识时退回 `xyz`，让挂载那一步去报错，比在这里静默丢弃字段好。
 */
export function toMountableLayer(wire: WireLayerSpec, fallbackId: string): LayerSpec {
  const url = wire.url ?? ""
  const spec: LayerSpec = {
    id: wire.id ?? fallbackId,
    type: asLayerType(wire.type) ?? "xyz",
    url,
  }
  if (wire.attribution) spec.attribution = wire.attribution
  const tiling = asTilingScheme(wire.tiling_scheme)
  if (tiling) spec.tilingScheme = tiling
  if (typeof wire.max_zoom === "number") spec.maxZoom = wire.max_zoom
  if (wire.layer_kind === "imagery" || wire.layer_kind === "map") spec.layerKind = wire.layer_kind
  if (wire.url_template) spec.urlTemplate = wire.url_template
  if (wire.crs) spec.crs = wire.crs
  if (wire.georeference_note) spec.georeferenceNote = wire.georeference_note
  if (wire.wmts_capabilities) spec.wmtsCapabilities = wire.wmts_capabilities
  if (wire.wmts_layer) spec.wmtsLayer = wire.wmts_layer
  if (wire.wmts_tile_template) spec.wmtsTileTemplate = wire.wmts_tile_template
  if (wire.wmts_style) spec.wmtsStyle = wire.wmts_style
  if (wire.wmts_tile_matrix_set_id) spec.wmtsTileMatrixSetId = wire.wmts_tile_matrix_set_id
  if (wire.wmts_format) spec.wmtsFormat = wire.wmts_format
  const dimensions = asStringMap(wire.wmts_dimensions)
  if (dimensions) spec.wmtsDimensions = dimensions
  return spec
}

/** 界面上一行展示用的署名：优先服务方要求的署名，其次授权声明。 */
export function attributionOf(wire: WireLayerSpec, fallback = ""): string {
  return wire.attribution?.trim() || wire.license_note?.trim() || fallback
}