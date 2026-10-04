# 遥感三维地球平台：Spec 文档

> 定位：技术亮点型全栈项目 ｜ 用途：作品集 ｜ 三维引擎：通用 CesiumJS（全球，无特定区域）
>
> 本文件是总纲。实现现状与规格的逐条差异见 [§13 Spec 与实现对账](#13-spec-与实现对账)；
> 启动方式、容器拓扑与数据来源署名见 [README](../README.md)。

## 0. 项目概述

**一句话**：一个数据源可插拔的遥感 WebGIS 平台，统一目录、标准服务发布，在三维地球上完成影像、地形、3D Tiles 的加载与时序对比。

**核心亮点**

1. **Provider 插件化**：新增数据源只加 `plugins/xxx/` 目录，不改核心代码。
2. **切片服务可插拔**：核心只依赖 `TilePublisher`；默认 TiTiler 动态出瓦片，GeoServer 作为可选适配器证明标准发布可替换。
3. **标准输出**：对外统一 XYZ / WMTS（默认路径必须可用）；WMS 与 GeoWebCache 随 GeoServer profile 提供。ArcGIS Pro、QGIS 可直接消费。
4. **双接入模式**：入库型（转 COG 发布）与引用型（登记远程服务）。

**非目标**：云检测、变化检测、大模型问数（仅保留扩展点）；实时卫星接收；多租户权限；ArcGIS Pro Add-in；商业卫星 API 的真实对接；默认路径引入 Redis / MinIO / Nginx / GeoServer。

## 1. Constitution（宪章）

| #   | 原则    | 具体约束                                                                   |
| --- | ----- | ---------------------------------------------------------------------- |
| C1  | 契约优先  | 核心代码只依赖 `DataSourceProvider` 与 `TilePublisher` 接口，禁止出现厂商专有逻辑           |
| C2  | 标准优先  | 目录对外用 STAC；栅格用 COG；地形用 quantized-mesh；模型用 3D Tiles；默认路径至少提供 XYZ 与 WMTS |
| C3  | 双接入模式 | 入库型与引用型共用同一 `layer` 输出结构                                               |
| C4  | 合规前置  | 每个数据源 spec 写明授权、条款、是否允许缓存；不抓取违反条款的瓦片；无授权的数据源不写猜测性接口                    |
| C5  | 前后端解耦 | 后端 ProviderRegistry + TilePublisherRegistry；前端 LayerTypeRegistry       |
| C6  | 可演示   | 每个里程碑产出可录屏成果                                                           |
| C7  | 作品集友好 | 仅用公开或自有数据；主线打磨优先于功能数量；默认路径容器数保持最小                                      |
| C8  | 性能预算  | 缓存命中瓦片 < 100ms；未命中 < 1s；地球端 ≥ 30fps（以实测为准，可调整）                         |

## 2. 技术栈与架构

默认路径尽量少容器。重组件用 Compose profile 打开，不进 `docker compose up`。

| 层级       | 默认选型                                                                | 可选（`--profile full` 或单项 profile）         | 职责                                       |
| -------- | ------------------------------------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| 前端       | Vite + Vue 3 + TypeScript + CesiumJS                                | OpenLayers 仅作后期 2D，经 `MapAdapter` 隔离     | 三维地球、卷帘、工具；用 `openapi-typescript` 对齐后端契约 |
| 后端       | Python 3.12 + FastAPI（挂载 TiTiler）                                   | —                                        | 目录 API、Provider 管理、任务、默认切片               |
| 数据库      | PostgreSQL + PostGIS                                                | —                                        | 元数据、空间检索、标注、图层、`job` 表                   |
| ORM / 迁移 | SQLAlchemy + GeoAlchemy2 + Alembic                                  | —                                        | 表结构与迁移                                   |
| 切片发布     | `TilePublisher`：默认 `titiler`                                        | `geoserver` 适配器（含 GWC）                   | 从 COG 出 XYZ/WMTS；GeoServer 补 WMS 与企业级缓存  |
| 对象存储     | 本地目录 + fsspec                                                       | MinIO（S3 兼容）                             | COG、地形、3D Tiles；换存储只改配置                  |
| 任务       | `job` 表 + 同镜像 worker 循环                                             | Redis + 轻量队列（如 arq）                      | 入库/转码；禁止把分钟级 GDAL 任务丢给 `BackgroundTasks` |
| 静态 / 反代  | 开发期 Vite 代理；生产期 Caddy 网关（同时发静态资源、反代 `/api` 与 `/cog`）        | Nginx                            | 需要独立缓存或 TLS 时再加                          |
| 部署       | Docker Compose                                                      | `profile: geoserver` / `redis` / `minio` | 默认三容器；GDAL/rasterio 只装在镜像内，不要求本机安装       |
| 工具链      | `ruff`（后端 lint）；`pnpm` + ESLint + `vue-tsc`（前端）                     | —                                        | lint 与测试目前靠本地命令，CI 尚未接入       |

```
默认（docker compose up）:
  postgis + api（FastAPI + TiTiler + job worker） + gateway（Caddy + 前端静态产物）

可选:
  docker compose --profile geoserver up   # OGC WMS + GWC
  docker compose --profile redis up       # 任务量大时
  docker compose --profile minio up       # 需要 S3 兼容存储时
```

软件分层（容器拓扑与 URL 路由见 README）：

```
Frontend: Cesium 地球 | 图层管理 | 卷帘 | 工具
          LayerTypeRegistry（wmts / xyz / cog / terrain / 3dtiles）
                     │ REST / OpenAPI
FastAPI Core: Catalog API | Layer API | Job API | ProviderRegistry | TilePublisherRegistry
     │                 │                         │
  PostGIS         TilePublisher              Provider 插件
                  (titiler 默认 /            (local_file / public_stac /
                   geoserver 可选)            arcgis_wayback / …)
对象存储抽象（fsspec）: 本地目录 或 MinIO
```

> 地形与 3D Tiles 不走切片服务。quantized-mesh 与 3D Tiles 由静态托管或第三方 URL 提供。
> 前端框架锁定 Vue 3：Composition API 适合图层状态；不引入 React。CesiumJS 官方示例是 vanilla，封装边界放在 `MapAdapter` / `LayerTypeRegistry`。

### 2.1 已拍板的取舍

1. **切片默认 TiTiler，GeoServer 可选。** 主线可演示、可被 QGIS 加 XYZ/WMTS。作品集要讲"标准 GIS 服务"时再开 GeoServer profile，证明 `TilePublisher` 可替换。两条路径都做进核心，只把 GeoServer 设为默认。
2. **前端必须 TypeScript。** 图层、卷帘、OpenAPI 契约没有类型会失控。框架用 Vue 3，不并行维护 React。
3. **入库任务不用 FastAPI `BackgroundTasks`。** COG 转换是分钟级、进程重启会丢。默认：`job` 表 + 同镜像内的 worker 循环。任务量上来再上 Redis/arq。`BackgroundTasks` 只允许秒级轻活。
4. **Caddy 网关取代"API 挂静态"。** 原结论是生产期不引反代（个人开发者会被反代配置拖死），但前端所有请求打 `/api/*` 而 `pnpm preview` 不读 Vite 代理，容器里必然一片 404，本机开发却完全正常、很难发现。改为默认经 Caddy 网关进入，网关同时发静态产物、反代 `/api`（剥前缀）与 `/cog`（原样透传）。容器数仍守在三个 —— 前端产物 COPY 进网关镜像，不再单起 web 容器。独立缓存层与 TLS 仍随 GeoServer 或以后的 CDN 再加。
5. **STAC 用 `pystac` 序列化，不上 pgSTAC。** 五张业务表 + `job` 够用。对外 Item 由库生成，禁止手拼 JSON。
6. **测试只压主契约。** 自动化覆盖：Provider 契约、目录检索、入库→COG→瓦片 URL、TilePublisher 适配器接口。`LayerTypeRegistry` 做纯函数单测。地球交互、卷帘手感以手动/录屏为准，不上 E2E 框架。

## 3. 三维地球数据来源策略

Cesium 视图按"图层类型 + URL"加载，来源与具体区域无关。ion、自建 URL 都是配置项，禁止把 ion 写死在视图核心。

| 数据类型     | 默认来源（现成）                                                                       | 可选扩展                                                    |
| -------- | ------------------------------------------------------------------------------ | ------------------------------------------------------- |
| 影像       | 可配置的全球底图（默认 Cesium ion 影像，可换成其他 XYZ/WMTS）；`public_stac` 引用；`arcgis_wayback` 引用 | 本地上传 → COG → `TilePublisher`（默认 TiTiler WMTS/XYZ）       |
| 地形       | 可配置；默认 Cesium ion 的 Cesium World Terrain                                       | 用户自建 quantized-mesh，登记为 `terrain` 类型图层（URL 指向静态托管或本地目录） |
| 3D Tiles | 可配置；默认 Cesium ion 资产                                                           | Google Photorealistic 3D Tiles（需 Key 与署名）；自有 3D Tiles   |

**说明**

- 地形作为一种图层类型，可在设置中切换 provider（ion / 自建 URL）。Cesium 同一时刻只用一个 terrain provider，切换即替换。
- 各服务的免费额度与条款以官网当前为准，落地前查官方文档。本文件不担保 ion / Wayback / STAC / Google 的额度仍然免费。

## 4. Spec 001：目录核心与 Provider 契约

### 4.1 用户故事

- 作为数据管理员，我能登记数据源并检索影像，支持时间、空间、云量过滤。
- 作为开发者，我只新增一个插件目录就能接入新数据源。

### 4.2 Provider 契约

```python
class DataSourceProvider(Protocol):
    id: str
    capabilities: set[str]   # {"search","ingest","tile_proxy","temporal"}

    def authenticate(self, config: dict) -> None: ...
    def search(self, bbox, datetime_range, filters) -> list[CatalogItem]: ...
    def get_layer_spec(self, item_id: str) -> LayerSpec: ...   # 返回前端可直接加载的图层描述
    def ingest(self, item_id: str) -> Job: ...                 # 仅入库型实现
```

```python
class TilePublisher(Protocol):
    id: str  # "titiler" | "geoserver"
    def publish(self, item_id: str, cog_href: str, *, datetime=None) -> LayerSpec: ...
    def unpublish(self, layer_id: str) -> None: ...
```

### 4.3 plugin.yaml 规范

```yaml
id: public_stac
name: Public STAC
version: 0.1.0
mode: reference            # reference | ingest
capabilities: [search, temporal]
credentials: []
license_note: "待确认：以所选公开 STAC 端点及数据许可为准"
cache_allowed: false
status: implemented        # implemented | skeleton
entrypoint: provider.py:PublicStacProvider
```

### 4.4 数据模型（PostGIS，简版）

| 表            | 关键字段                                                                             |
| ------------ | -------------------------------------------------------------------------------- |
| `provider`   | id, name, mode, status, config_json, enabled                                     |
| `collection` | id, provider_id, title, description                                              |
| `item`       | id, collection_id, geometry, acquired_at, cloud_cover, asset_href, access_mode   |
| `layer`      | id, item_id / collection_id, type, url, style_json, time_dimension, publisher_id |
| `annotation` | id, geometry, properties_json, created_at                                        |
| `job`        | id, type, status, progress, error, payload_json, created_at, updated_at          |

对外 `GET /items` 的 Item 用 `pystac` 序列化。内部表保持精简，不上 pgSTAC。

### 4.5 验收标准

> 勾选只依据代码与测试能核实的事实；不成立或无法自动核实的条目保持未勾，并写明原因。
> 与 `specs/*/spec.md` 的「状态」不一致时，以本节为准。

- [x] 新增 `plugins/xxx/` 后重启，`GET /providers` 出现该插件，核心零改动。
- [x] `GET /items?bbox=&datetime=&cloud_cover_lt=` 返回 STAC 风格 Item 列表。三个参数都在路由签名里，序列化由 `app/catalog/stac.py` 的 `pystac.ItemCollection(...).to_dict()` 产出。
- [x] 引用型与入库型 Item 输出同一 `layer` 结构：两者都返回 `LayerSpec`，都经 `GET /items/{item_id}/layer` 暴露。
- [x] `plugin.yaml` 缺必填项时加载失败并给出明确错误，不影响其他插件。
- [ ] 切换 `TilePublisher` 实现后 `layer.url` 仍能被 `LayerTypeRegistry` 加载。**部分不成立**：核心确实没有 `if publisher == ...`（有守卫测试），`titiler` 分支由 `tests/test_tile_service.py` 的真实请求守着；但 `geoserver` 分支的 `publish()` 只拼字符串、零网络调用，而 compose 里既无 `geoserver` 服务也无任何 profile，换过去会拿到指向不存在主机的图层。见 §13 第 9 条。

---

## 5. Spec 002：入库、发布与缓存

**流程**：上传/登记 → 写入 `job`（排队）→ worker 取任务 → 元数据提取（rasterio/GDAL，仅在镜像内）→ 转 COG 到 fsspec 存储 → 写入 `item` → `TilePublisher.publish`（默认 TiTiler，按 datetime 区分时相）→ 返回可访问的 XYZ/WMTS URL。

GeoServer profile 开启时，同一 `publish` 走 GeoServer REST（含 TIME 维度与 GWC）。缓存命中率：默认路径测 TiTiler 前的 HTTP 缓存（若未部署缓存层，则报告动态切片耗时，并标明"无中间缓存"）；GeoServer 路径测 GWC 命中率。禁止把"无缓存"报成命中。

**验收标准**

> 勾选只依据代码与测试能核实的事实。以下第 5 条不成立。
- [x] 上传一景 GeoTIFF，自动生成 Item 与可访问的 WMTS 或 XYZ 地址（默认 TiTiler 路径，不依赖 GeoServer 容器）。TiTiler 的 XYZ / WMTS / preview 由 `tests/test_tile_service.py` 以真实请求验证。
- [x] 同一区域多时相可区分 —— 但靠的是**每景各自入库成独立图层**（`time_dimension` 落库），而不是给切片端点传 `datetime`：`tiles.openapi.yaml` 里没有 `datetime` 参数，`datetime` 是 `/items` 与 provider 检索的参数。
- [x] 任务状态可查询（`GET /jobs`、`GET /jobs/{id}`、`DELETE /jobs/{id}`）；API 进程重启后未完成的 `job` 由 `recover_interrupted` 回收，不静默丢失。
- [x] 展示切片耗时：`GET /tiles/timing` 真实发起一次请求；无缓存层时报 `cache: "none"`，有缓存层也只报 `"unverified"` 而不编造命中率。
- [ ] 默认路径可被 QGIS 直接添加；GeoServer profile 下可被 ArcGIS Pro 以 WMTS/WMS 添加。**不成立**：`use_epsg=true` 让 `SupportedCRS` 写成 `EPSG:3857` 是 §12 第 3 条的推断，从未在 ArcGIS Pro 或 QGIS 里实测；且「GeoServer profile」目前根本不存在（compose 无该服务、无 `profiles:`），WMS 更无从谈起。
- [x] 本机无需安装 GDAL：GDAL/rasterio 是可选依赖（`pyproject.toml` 的 `gdal` extra），Compose 镜像内自带。**注意**要在本机跑后端测试仍需 `pip install -e ".[dev,gdal,postgres]"`。

---

## 6. Spec 003：三维地球视图

**用户故事**：我能在地球上叠加影像、地形、3D Tiles，独立开关并调节透明度。

**验收标准**

> 勾选只依据代码与测试能核实的事实。以下第 1 条不成立。
- [ ] 默认加载全球地形与影像，启动即可浏览。**部分不成立**：默认底图是 OpenStreetMap（全球影像，成立），但默认地形是 `ellipsoid://` —— 一个裸椭球，**没有任何地形**。全球地形（Cesium World Terrain）只在设了 `VITE_ION_TOKEN` 时才生效，3D Tiles 默认不加载。底图与地形 URL 确实来自配置、不写死在视图核心，这部分成立。
- [x] 三类数据独立开关，透明度可调（`App.vue` 的 `visible` 与 `onLayerOpacity`）。
- [x] 图层由 LayerTypeRegistry 创建，新增类型不改视图核心。
- [x] 3D Tiles 参数可调（`setMaximumScreenSpaceError` 接进 `App.vue` 的 watch），FPS 记录在 `#fps` 节点。**注意**默认不加载 3D Tiles，需自行配置 `VITE_TILESET_URL` 才能验证这条。
- [x] 第三方数据（ion、公开 STAC、Wayback）显示署名：`attribution` 贯穿底图、地形、挂载图层与卷帘两侧。**但**卷帘的三个演示场景硬编码了两个第三方瓦片服务（Esri World Imagery、CARTO），它们只由前端自撰署名、无 `license_note`，与宪章 C4 及 README「不内置第三方地图地址」的自我要求不符。见 §13 第 10 条。

---

## 7. Spec 004：时序卷帘

**用户故事**：我能拖动分隔条，对比同一区域两个时间的影像。

**实现**：两个 `ImageryLayer` 分别设置 `splitDirection = LEFT / RIGHT`，`scene.splitPosition` 由分隔条驱动；两侧时间来自 `TilePublisher` 的 `time`/`datetime` 参数、公开 STAC 资产 URL，或 Wayback 版本。

**验收标准**

> 勾选只依据代码与测试能核实的事实。三条都无法自动核实：一条不成立。
- [ ] 拖动分隔条流畅无明显卡顿。**无法自动核实**：卷帘逻辑（`clampSplit` / `splitFromPointer`）有单测，但"流畅"是主观手感，宪章 C6 也规定这类以手动或录屏为准。
- [ ] 左右两侧时间可独立切换。逻辑成立（`App.vue` 有独立的 `leftId` / `rightId` 与两条 watch），但没有自动化测试覆盖，故不勾。
- [ ] 同时支持"本地入库多时相"、"公开 STAC 多时相"与"Wayback 历史版本"三种来源。**不成立**：`swipe.ts` 的 `SwipeSource` 声明了这三种，但 `DEMO_SCENES` 里对应的三个 URL 实际是 OpenStreetMap、Esri World Imagery、CARTO dark_all —— 都不是本地入库的 COG、不是 STAC 条目、也不是 Wayback 历史版本。标签与内容不符。见 §13 第 11 条。

> 遗留：三种来源的时间语义并不等价 —— 本地入库按 `acquired_at` 取值、公开 STAC 按
> `datetime` 区间检索、Wayback 只有离散的历史版本、没有连续时相。界面上三者的
> "选时间"行为因此不完全一致，这个差异尚未在文档里说明。

---

## 8. Spec 005：图层管理与工具

| 功能   | 验收标准                                                                    |
| ---- | ----------------------------------------------------------------------- |
| 添加图层 | 点「图层」弹出能铺上地球的源。有时间维才选时间，默认该源的最近一景。地址含 `{z}` 就挂到三维地球。底图和地形来自地球配置，不出现在弹层里 |
| 图层管理 | 已经挂上的行仍可显隐、排序、透明度、删除，并按数据源分组。合并掉的是选源，不是这些行                              |
| 标注   | 点/线/面绘制，保存到 PostGIS，导出 GeoJSON                                          |
| 量算   | 距离、面积、高度；结果可复制                                                          |
| 飞行定位 | 坐标输入、图层范围定位、书签                                                          |

---

## 9. Spec 006：数据源插件

| 插件               | 模式     | 状态    | 说明                                                                |
| ---------------- | ------ | ----- | ----------------------------------------------------------------- |
| `local_file`     | 入库型    | P0 实现 | 用户上传 GeoTIFF，主链路基准                                                |
| `public_stac`    | 引用型    | P0 实现 | 公开 STAC。默认 Sentinel-2，集合可改为 Landsat。不写死卫星波段。端点与许可以官方为准            |
| `gibs`           | 引用型    | P0 实现 | NASA GIBS 官方 WMTS，全球多时相，适合卷帘。不另存瓦片                                |
| `arcgis_wayback` | 引用型    | P0 实现 | 历史影像版本。使用条款以 Esri 官方为准                                            |
| `tianditu`       | 引用型    | 需 Key | 天地图开发者平台官方 WMTS。无 Key 不请求。展示须署名并标注审图号。坐标系记为 EPSG:4490。不抓取瓦片       |
| `tencent_map`    | 引用型    | 需 Key | 腾讯位置服务官方 SDK / JS API。电子地图，不是遥感影像。坐标系 GCJ-02，不直接叠到 WGS84 地球，不抓取瓦片 |
| `google_tiles`   | 引用型    | 需 Key | 仅 Google Maps Platform 的 Map Tiles API。不抓取 Google Earth 瓦片        |
| `gee`            | 引用/导出型 | 仅骨架   | 未接入。Earth Engine 需 service account，且导出的是 GeoTIFF 而非瓦片地址，落地路径是走入库转 COG 再发布。不作为演示主路径               |
| `jilin1`         | 入库型    | 仅骨架   | 无授权。不写真实 API                                                      |
| `siwei`          | 引用型    | 仅骨架   | 四维地球。商业数据，无授权与公开接口文档                                              |
| `shiji`          | 引用型    | 仅骨架   | 世纪空间。同上                                                           |
| `beijing1`       | 入库型    | 仅骨架   | 同上                                                                |
| `custom_xyz`     | 引用型    | P0 实现 | 用户自备合法地址。不内置第三方 URL，不解析地图官网                                       |

适合演示的公开来源与逐项署名要求见 README 的「数据来源与署名」一节；额度与条款以各官网当前说明为准，本文不实时担保。

**挂到地球**：选源发生在「图层」里，不再单独占一块数据源区。弹层只列出清单标明可铺、且状态为可用的源。GIBS 与 Wayback 直接给出 `{z}/{x}/{y}`。公开 STAC 必须带上地图范围，否则检索拒绝。本地文件的检索固定为空，地址等上传发布之后才有，因此不进弹层。未实现、需配置、以及不提供瓦片的源（如腾讯地图）也不进弹层。底图和地形来自地球配置，不在插件列表里。

有时间维的源才出现时间选择，没有的跳过。默认「最近」按源区分：GIBS 用当前日期减去处理延迟（5 天），不用时钟上的今天；Wayback 把清单按日期从新到旧排列后取最新版本；公开 STAC 在范围上再加时间，取最新一景。选定的时间经检索接口的 `datetime` 传给插件。确认后走现有的挂载：地址里有 `{z}` 就铺到三维地球。挂上之后，图层行仍负责显隐、透明度和删除。

`LayerSpec` 增加 `crs` 与 `attribution`。国内电子地图常见 GCJ-02，天地图影像按 CGCS2000（EPSG:4490）声明。未做显式转换的 GCJ-02 图层不得叠到 WGS84 地球上。

**自定义 XYZ**
接入本质是 URL 模板加投影声明，而不是再写一个厂商插件。`LayerSpec` 因此包含：

- `url_template`：支持 `{z}` `{x}` `{y}`，以及可选的 `{time}`。`{$z}` 与 `{$ovtm=time}` 会先收成这两种写法。
- `tiling_scheme`：`WebMercator` 或 `Geographic`。
- `max_zoom`：最大级别。
- `layer_kind`：`imagery`（影像）或 `map`（普通地图）。

时序对比沿用同一模板，把时间填进 `{time}`。Wayback 瓦片地址和 GeoServer 的 `time` 参数都落在这个结构上。

**合规**：用户自行从地图官网解析瓦片地址，可能违反数据方条款。宪章 C4 禁止抓取违反条款的瓦片。`custom_xyz` 只接受用户声明为合法的地址，插件和仓库都不预置未授权 URL。README 写明这一点。

**骨架插件的定义**：包含 `plugin.yaml`（`status: skeleton`）、Provider 类与方法签名，`search`/`ingest` 抛出 `NotImplementedError` 并附说明。目的是展示扩展点，而不是声称已对接。

**对外兼容**：QGIS 走默认 XYZ/WMTS。ArcGIS Pro 走 WMTS；若默认 TiTiler 的 WMTS 能力文档不足，用 GeoServer profile 完成 Pro 演示，并在 README 写明走哪条路径。不得把"只有 XYZ"说成已交付 WMS。

**验收标准**

> 勾选只依据代码与测试能核实的事实。第 2 条部分不成立。
- [x] 现场演示：加入 `public_stac` 或 `arcgis_wayback` 插件，图层自动出现在前端，核心代码零改动。
- [ ] 骨架插件能被注册表识别并在界面标注"未实现"。**部分不成立**：注册表识别成立（`GET /providers` 返回它们，`status: skeleton`，且有守卫测试禁止 `implemented` + `ready` 的插件在 `search()` 里抛 `NotImplementedError`）；但**界面上没有任何"未实现"标注** —— 选源弹层按 `drape === true && availability === "ready"` 过滤，骨架与需 Key 的源根本不进弹层，用户看不到也标不了。
- [x] `public_stac` 无需用户注册即可检索并加载至少一景公开影像（默认端点 Element 84 Earth Search 的 `sentinel-2-l2a`）。

---

## 10. 里程碑（约 7 周）

| 周    | 产出                                                                |
| ---- | ----------------------------------------------------------------- |
| W1   | Constitution、001/002 spec、数据模型、Compose 默认三容器（postgis + api + gateway） |
| W2–3 | 本地入库 → COG → TiTiler XYZ/WMTS + `job` 可查询；可选再接通 GeoServer profile |
| W4   | Cesium 主界面（Vue 3/TS）：全球地形/影像、3D Tiles、图层管理                        |
| W5   | 时序卷帘、标注、量算、飞行定位                                                   |
| W6   | 插件机制落地：`public_stac`、`arcgis_wayback`                             |
| W7   | 骨架插件、性能指标、文档；可选 GeoServer 适配器演示与自建地形                              |

---

## 11. 作品集交付清单

> 勾选只依据仓库里实际存在的东西。
- [ ] README：一句话定位、架构图、亮点 GIF（卷帘、插件热加载）；写明默认三容器与可选 profile。**部分完成**：定位、架构图、默认三容器都有；**亮点 GIF 没有**（仓库内零图片文件）；**可选 profile 没写**（`geoserver` / `redis` / `minio` 三个 profile 在 compose 里都不存在，见 §13 第 9 条）。
- [x] `/specs` 精选（constitution + 001 + 006）；每份 feature spec 控制在可扫读长度，细节进 plan/contracts，不在本总纲膨胀。
- [ ] 性能指标表：切片耗时、缓存命中率（或明确无缓存）、首屏时间、FPS。**未做**（已明确延后）。`/tiles/timing` 是真实采样的，但还没有汇总成表。
- [x] 数据来源与署名说明页（README「数据来源与署名」）。
- [ ] 一键启动：`docker compose up`（仅默认三容器即可演示目录、入库切片、地球）。**未实测**：配置齐全，但本机没有 Docker，`docker compose up` 与 `scripts/smoke.py` 从未实际跑过。这是整条生产路径唯一的证据空白。

---

## 12. 待确认事项

1. `public_stac` 默认端点与集合 ID（Sentinel-2 公开 COG STAC）。当前落在 `plugins/public_stac/plugin.yaml`（Element 84 Earth Search，`sentinel-2-l2a`），许可与署名以该数据集当时的官方说明为准。
2. 各第三方服务（ion、Wayback、Google、TiTiler/GeoServer 版本与许可）的最新条款、免费额度与社区版许可，以官网为准。MinIO 社区版功能与许可近期有过调整，启用 profile 前再查。
3. ~~TiTiler 默认路径的 WMTS GetCapabilities 是否足以让 ArcGIS Pro 一键添加。~~ **已确认可行**：`use_epsg=true` 让 `ows:SupportedCRS` 写成 `EPSG:3857` 而不是 `urn:ogc:def:crs:EPSG::3857`，这是 Pro 直接添加的关键。WMTS Layer 标识由 COG 文件名推导，入库路径下文件名即 item id，所以同一景反复取值标识不变、客户端重连时认得出还是同一层。Pro 演示不必改走 GeoServer profile。
4. 宪章技术约束已在 `.specify/memory/constitution.md` v1.3.0 与本文件对齐。

---

## 13. Spec 与实现对账

改造前六个 Spec 的 84 个任务已全部勾完，但其中若干「成功标准」在代码里并不成立 —— 勾的是文档产出，不是能力可用。逐条列出并说明处理方式，而不是把 spec 悄悄改掉。

各节验收标准（§4.5、§5、§6、§7、§9）与交付清单（§11）现已逐条重判：能核实的勾上，不成立或无法自动核实的保持未勾并写明原因。**若本节与那些复选框冲突，以本节为准。**

下面是改造过程中发现、且已处理的漂移：

| # | Spec 原先声称 | 实际状况 | 处理 |
|---|---|---|---|
| 1 | 002：上传 GeoTIFF 自动生成可访问的 WMTS 或 XYZ 地址 | `publishers/registry.py` 只写死一个 URL 字符串，**没有任何进程会响应它** —— titiler 不是依赖也没挂载 | TiTiler 路由挂进 FastAPI 同一进程；补 XYZ / WMTS / preview 三套地址；路径校验与越界 404 |
| 2 | 002：展示切片耗时 | `/tiles/timing` 是个空壳，测的是自己减自己的耗时 | 改为真实发起一次请求；未采样时如实报告而不是返回编造的 0 |
| 3 | 002：两个 worker 不得领同一任务 | 单进程单线程轮询，碰巧成立 | 领取改成条件更新 `WHERE status='queued'` 看 rowcount；补真并发测试 |
| 4 | C7：默认路径三个容器 = postgis/api/web | compose 里前端用 `pnpm preview`，不读 Vite 代理，`/api/*` 在容器里必然 404，而本机开发正常 | 网关取代 web 容器并同时发静态产物；容器数仍为三个；宪章 C7 相应修订 |
| 5 | 001：切换 publisher 后核心不出现 `if publisher == ...` | 成立，但配置项名 `titiler_prefix` 把实现名带进了核心（被守卫测试抓出） | 配置改为实现中立的 `tile_service_prefix`；守卫测试扩到 `app/` 全部（除 `publishers` 包） |
| 6 | 002：任务状态可查询，进程重启后未完成任务不得静默丢失 | 重启恢复是有的，但前端没有任何入口，只能手 curl | 补前端上传/轮询/任务列表/取消闭环；补 `GET /jobs` 与 `DELETE /jobs/{id}` |
| 7 | 006：加入插件目录即零改动生效 | 成立。但 `drape`/`picker`/`availability` 三个前端依赖的字段既不必填也无取值校验，`availability` 还有两处真相源 | 三者进必填契约并校验；`availability` 明确 manifest 为基线、provider 认证后可收紧 |
| 8 | 006：`gee` 为 P2 可选 | manifest 写 `implemented`，但 `search()` 恒抛 `NotImplementedError` —— 界面上看起来能用，点进去才发现不行 | 改为 `skeleton`；新增守卫测试：任何 `implemented` + `ready` 的插件，`search()` 抛 `NotImplementedError` 即测试失败 |

本轮核对验收标准时又查出三条，逐条列出：

| # | 文档原来说 | 实际状况 | 处理 |
|---|---|---|---|
| 9 | §2 与 §2.1：`GeoServer` 是"可选适配器"，用 `--profile geoserver` 打开；`--profile redis` / `minio` 同理 | compose 里**没有任何 `profiles:`**，也没有 `geoserver` 服务。而 `GeoserverPublisher.publish()` 的字节码里**零个方法调用** —— 它只按 `http://geoserver:8080/...` 拼字符串，从不建 datastore、不注册 coverage layer。设 `WEBGIS_DEFAULT_PUBLISHER=geoserver` 后入库会**报成功**，图层却指向一个永远解析不了的主机 | 验收标准标为不成立。修法待定：要么显式标为 skeleton 并在选择时拒绝，要么真正实现 REST 注册并补 compose profile。注意 `--profile X` 在没有匹配服务时**不报错**，只是照常起默认三容器 —— 静默做错事 |
| 10 | 宪章 C4「不抓取违反条款的瓦片」；README「不内置任何第三方地图地址」 | `frontend/src/map/swipe.ts` 的 `DEMO_SCENES` 硬编码三个第三方瓦片 URL，其中 `services.arcgisonline.com`（Esri World Imagery）与 `basemaps.cartocdn.com`（CARTO）在任何 `plugin.yaml` 里都没有、也没有 `license_note`，只有前端自撰的署名行。且它们被标注为 `local` / `stac` / `wayback`，与实际内容（三个都是普通底图）不符 | 待处理。选项：换成真正走 provider 的图层、改成需显式配置才启用、或补 `license_note` 并把标签改成如实描述 |
| 11 | §7 验收：同时支持本地入库 / 公开 STAC / Wayback 三种来源做卷帘 | `SwipeSource` 声明了三种，`DEMO_SCENES` 也给了三个场景，但没有任何一个真的接了本地入库的 COG 或 STAC 条目 —— 卷帘目前只能在三个硬编码底图之间对切 | 与第 10 条同源，一并处理 |

此外还有两处不是 Spec 问题而是实现自相矛盾，一并在此记录：

- **表结构有两套真相**：`main.py` 启动时 `create_all`（只补缺失的表，不改已有表），Alembic 又硬编码 sqlite 地址、与应用连的库不是同一个。漂移要到某条查询报 `no such column` 才暴露。已删 `create_all`，迁移成为唯一来源，启动时校验版本、落后即拒绝启动。
- **`POST /providers/{id}/search` 与整个切片面没有契约**：契约里记了 6 个端点、6 个 Layer 字段，实现早已是 11 个端点、21 个字段。已补齐三份 OpenAPI 并新增切片面契约，另加守卫测试（`tests/test_contracts.py`）防止再次漂移。

