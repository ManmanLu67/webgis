# 数据模型：目录核心

## 数据源（`provider`）

| 字段 | 规则 |
|---|---|
| id | 字符串，必填，唯一，与插件目录名一致 |
| name | 字符串，必填 |
| mode | 枚举 `reference` 或 `ingest`，必填 |
| status | 枚举 `implemented`、`skeleton` 或 `error`，必填 |
| config_json | 对象，必填，默认 `{}` |
| enabled | 布尔，必填，默认 true |
| license_note | 字符串，必填（仅当状态为 error 时可以空） |
| cache_allowed | 布尔，必填 |
| error | 字符串，可空；该包加载失败时写入 |

停用的数据源不出现在默认列表中，其条目也不参与检索。行仍保留。

## 集合（`collection`）

| 字段 | 规则 |
|---|---|
| id | 字符串，必填，唯一 |
| provider_id | 必填，引用数据源 |
| title | 字符串，必填 |
| description | 字符串，默认空 |

## 条目（`item`）

| 字段 | 规则 |
|---|---|
| id | 字符串，必填，唯一 |
| collection_id | 必填，引用集合 |
| minx, miny, maxx, maxy | 数字，必填，minx ≤ maxx，miny ≤ maxy，经度 -180..180，纬度 -90..90 |
| acquired_at | 时间戳，必填 |
| cloud_cover | 0..100 的数字或空 |
| asset_href | 字符串，必填 |
| access_mode | 枚举 `reference` 或 `ingest`，必填 |

检索：矩形与条目范围相交；若给出时间窗，获取时间必须落在窗内；若设置 `cloud_cover_lt`，`cloud_cover` 必须非空且严格小于该值。

## 图层（`layer`）

| 字段 | 规则 |
|---|---|
| id | 字符串，必填，唯一 |
| item_id | 可空，引用条目 |
| collection_id | 可空，引用集合 |
| type | 枚举 `wmts`、`xyz`、`cog`、`terrain`、`3dtiles`，必填 |
| url | 字符串，必填 |
| style_json | 对象，必填，默认 `{}` |
| time_dimension | 字符串，可空 |
| publisher_id | 字符串，必填 |

`item_id` 与 `collection_id` 恰好设置一个。返回给客户端的文档是 `type`、`url`、`style`、`time_dimension`。`publisher_id` 会存储，但地图客户端选择加载器时不需要它。

## 只出不落的图层字段

下列字段不进 `layer` 表，由 `DataSourceProvider.get_layer_spec()` 在响应里给出，
因此不入库也能表达（`specs/001-catalog-provider/contracts/catalog.openapi.yaml` 的 `Layer`）：

| 字段 | 规则 |
|---|---|
| url_template | 字符串，可空。支持 `{z}` `{x}` `{y}` 与可选 `{time}` |
| tiling_scheme | 枚举 `WebMercator`、`Geographic`，默认 `WebMercator` |
| max_zoom | 整数，可空。给 Cesium 的 `maximumLevel`，避免它去请求不存在的级别 |
| layer_kind | 枚举 `imagery`、`map`，默认 `imagery` |
| crs | 字符串，默认 `EPSG:4326`。只用于署名与合规声明，不参与渲染 |
| attribution | 字符串，默认空。展示署名 |
| wmts_* | 真 WMTS 的两种编码，见契约 |
| georeference_note | 字符串，默认空。需要说清的重投影或基准差异，也用来说明轨道间隙来自源数据 |
| level_zero_tiles_x | 整数，默认 2。Geographic 零级列数。GIBS 的 EPSG:4326 取 10 |
| level_zero_tiles_y | 整数，默认 1。Geographic 零级行数。GIBS 取 5 |
| level_offset | 整数，默认 0。URL 级别 = Cesium 级别 + 偏移。GIBS 取 3 |
| tile_pixel_size | 整数，默认 256。GIBS 为 512 |

## 关系

数据源 1—N 集合 1—N 条目 1—N 图层。集合级图层没有条目。

## 状态

数据源的 `enabled` 切换可见性。包加载失败把 `status` 设为 `error`，并且不替换已经有效的同标识数据源。
