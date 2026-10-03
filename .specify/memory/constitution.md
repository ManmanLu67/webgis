<!--
同步影响说明
- 版本变化：1.1.0 → 1.2.0
- 升级理由：C2 增加坐标系必须显式声明，以及署名、审图号写入 attribution。
- 版本变化（前次）：1.0.0 → 1.1.0
- 升级理由：技术约束改为与 docs/SPEC.md v0.3 一致。原则标题不变。C1、C2、C5、C7 的措辞已对齐，避免与新的默认栈矛盾。不是 2.0.0：没有删除原则，义务仍在。当时还没有按 1.0.0 写过功能计划。
- 修改的原则：
  - C1 契约优先：只依赖 DataSourceProvider → DataSourceProvider 与 TilePublisher
  - C2 标准优先：一条路径上同时要求 WMTS/WMS/XYZ/OGC → 默认路径必须提供 XYZ 与 WMTS；WMS 与 GeoWebCache 只在 GeoServer profile
  - C5 前后端解耦：增加 TilePublisherRegistry；地形和 3D Tiles 不走切片发布器
  - C7 作品集友好：增加默认容器数量最少的要求
- 新增章节：无
- 删除章节：无
- 暂缓项：无
- 提交宪章文件前删除这段 HTML 注释。
-->

# 遥感三维地球平台 Constitution

## Core Principles

### I. 契约优先（C1）

核心代码 MUST 只依赖 `DataSourceProvider` 与 `TilePublisher` 接口。厂商专有逻辑 MUST 留在 `plugins/<id>/` 或具体 `TilePublisher` 适配器中，禁止进入 Catalog、Layer、Job 核心。新增数据源 MUST 只增加插件目录。切换切片实现 MUST NOT 在核心里写 `if publisher == ...`。

理由：插件化与切片可替换是作品集主亮点。核心一旦出现厂商分支，后续数据源和发布后端都会改核心。

### II. 标准优先（C2）

目录对外 MUST 使用 STAC 风格 Item，并由 `pystac` 序列化，禁止手拼 JSON，不上 pgSTAC。入库栅格 MUST 发布为 COG。默认路径 MUST 至少提供 XYZ 与 WMTS。WMS 与 GeoWebCache MUST 只在 GeoServer profile 下提供。地形 MUST 使用 quantized-mesh。三维模型 MUST 使用 3D Tiles。禁止发明仅内部可消费的私有瓦片协议作为主输出。禁止把「只有 XYZ」称为已交付 WMS。每条图层 MUST 在 `LayerSpec.crs` 中写明坐标系。GCJ-02 不得当作 WGS84 直接叠到地球上。公开发布所需的署名和审图号 MUST 写入 `LayerSpec.attribution`。

理由：QGIS 必须能直接添加默认路径。ArcGIS Pro 的 WMS/WMTS 演示可以走 GeoServer profile，并在 README 写明路径。

### III. 双接入模式（C3）

入库型（转 COG 再发布）与引用型（登记远程服务）MUST 输出同一 `layer` 结构。前端 MUST 按图层类型与 URL 加载，不得按数据源厂商分支渲染。

理由：卷帘、图层管理和地球视图只认图层，不认来源。

### IV. 合规前置（C4）

每个数据源 spec MUST 写明授权、使用条款和是否允许缓存。禁止抓取违反条款的瓦片。没有授权和接口文档的数据源 MUST 只提供骨架（`status: skeleton`），`search` / `ingest` MUST 抛出 `NotImplementedError` 并附说明，禁止编写猜测性 API。

理由：商业卫星与第三方底图的合规风险高于功能收益。

### V. 前后端解耦（C5）

后端 MUST 通过 `ProviderRegistry` 发现插件，通过 `TilePublisherRegistry` 选择切片实现。前端 MUST 通过 `LayerTypeRegistry` 创建图层（`wmts` / `xyz` / `cog` / `terrain` / `3dtiles`）。新增图层类型 MUST 不改视图核心。地形与 3D Tiles MUST NOT 走切片服务；quantized-mesh 与 3D Tiles MUST 走静态托管或第三方 URL。

理由：发布链与地球渲染链职责不同。把地形和模型绑进切片服务会让默认路径离不开 GeoServer。

### VI. 可演示（C6）

每个里程碑 MUST 产出可录屏的运行结果。没有可启动界面或可调用 API 的里程碑视为未完成。默认地球 MUST 在无本地影像时仍能浏览全球地形与影像。底图与地形 URL MUST 来自配置，禁止把 Cesium ion 写死在视图核心。

理由：作品集以可见成果为准，不以文档数量为准。

### VII. 作品集友好（C7）

演示数据 MUST 限于公开数据或自有数据。主线打磨优先于功能数量。`docker compose up` 的默认路径 MUST 只启动 postgis、api、web 三个容器。GeoServer、Redis、MinIO MUST 用 Compose profile 隔离，不得进入默认路径。非目标（云检测、变化检测、大模型问数、实时卫星接收、多租户权限、ArcGIS Pro Add-in、商业卫星真实对接）MUST NOT 进入主线实现；只允许保留扩展点。

理由：范围膨胀和服务数量会挤掉卷帘、插件和可启动演示。

### VIII. 性能预算（C8）

缓存命中瓦片 MUST 以小于 100ms 为目标。未命中 MUST 以小于 1s 为目标。地球端 MUST 以不低于 30fps 为目标。指标以实测为准，可以调整，但调整 MUST 写入性能记录并说明测量条件。切片耗时 MUST 可查询或可展示。有缓存层时 MUST 展示命中率；没有中间缓存时 MUST 标明「无中间缓存」，禁止把动态切片报成命中。

理由：可量化指标是作品集交付清单的一部分。

## Technology Constraints

- 前端：Vite + Vue 3 + TypeScript + CesiumJS。OpenAPI 客户端类型 MUST 由 `openapi-typescript` 从后端契约生成。OpenLayers 仅作后期 2D 备选，MUST 经 `MapAdapter` 隔离，不得直接进入主视图。不引入 React。
- 后端：Python 3.12 + FastAPI。默认切片 MUST 挂载 TiTiler，与 API 同一技术栈。职责限于目录 API、Provider 管理、Job、默认切片。
- 数据库：PostgreSQL + PostGIS，一个容器。表结构与迁移 MUST 使用 SQLAlchemy + GeoAlchemy2 + Alembic。
- 切片发布：核心只依赖 `TilePublisher`。默认实现 `titiler`（COG → XYZ/WMTS）。`geoserver`（含 GWC）MUST 是可选适配器，由 `--profile geoserver` 启用。
- 对象存储：默认本地目录，经 fsspec 读写。MinIO 仅 `--profile minio`。换 S3 兼容存储 MUST 只改配置。
- 任务：入库与转码 MUST 写入 `job` 表，由同镜像内的 worker 循环领取。分钟级 GDAL 任务 MUST NOT 使用 FastAPI `BackgroundTasks`。`BackgroundTasks` 只允许秒级轻活。Redis 与轻量队列（如 arq）仅 `--profile redis`。
- 静态与反代：开发期 Vite 代理；生产期 FastAPI 挂静态资源。Caddy / Nginx 不是默认组件。
- 部署：`docker compose up` MUST 只拉起 postgis + api + web。GDAL 与 rasterio MUST 只安装在 API 镜像内，不要求本机安装。
- 工具链：Python 用 `uv` + `ruff`；前端用 `pnpm`；`pre-commit`；GitHub Actions 至少跑 lint 与契约/入库测试。
- 测试范围：自动化 MUST 覆盖 Provider 契约、目录检索、入库到 COG 再到瓦片 URL、`TilePublisher` 适配器接口，以及 `LayerTypeRegistry` 纯函数。地球交互与卷帘手感以手动或录屏为准，不上端到端浏览器框架。
- 插件清单：`plugin.yaml` 必填项缺失时，该插件加载 MUST 失败并给出明确错误，且 MUST NOT 阻止其他插件加载。
- 插件优先级：`local_file`、`public_stac`、`arcgis_wayback` 为 P0。`public_stac` MUST 是通用公开 STAC 客户端，默认配置指向无需认证的公开 Sentinel-2 COG，具体端点以官方为准并写入 `license_note`。`gee` 与 `google_tiles` 为 P2 可选。`jilin1`、`beijing1` 仅骨架。`google_tiles` 仅官方 Map Tiles API，禁止抓取 Google Earth 瓦片。

## Delivery Gates

功能按 `docs/SPEC.md` 的 Spec 001–006 顺序交付，后一 Spec 不得推翻前一 Spec 的契约：

1. 目录核心与 Provider 契约
2. 入库、发布与缓存
3. 三维地球视图
4. 时序卷帘
5. 图层管理与工具
6. 数据源插件

每个 Spec MUST 先有可验证的 spec / plan / tasks，再实现。验收标准以 `docs/SPEC.md` 对应章节为准；实现若发现标准不可测，MUST 先改 spec，再改代码。

## Governance

本宪章是 Spec Kit 治理文件，约束后续 `/speckit-specify`、`/speckit-plan`、`/speckit-tasks`、`/speckit-implement`。产品范围、用户故事与验收标准的总纲是 `docs/SPEC.md`。二者冲突时，先改其中一方并在同一次变更中同步另一方，禁止长期并存两套原则。

- 版本：语义化。不兼容的原则删除或重定义为 MAJOR；新增或实质扩展原则为 MINOR；措辞澄清为 PATCH。
- 修订：修改原则 MUST 更新本文件版本与 `Last Amended`，并在 Sync Impact Report 中说明，直到该说明在提交前被移除。
- 合规审查：计划与实现 MUST 能指出所遵守的原则编号（C1–C8）。无法对应原则的范围扩展默认拒绝。
- 复杂度：引入新服务、新前端框架或新数据协议 MUST 在 plan 中说明为何现有栈不够用。默认路径增加第四个容器视为违反 C7，除非先修订本宪章。

**Version**: 1.2.0 | **Ratified**: 2026-09-28 | **Last Amended**: 2026-09-28
