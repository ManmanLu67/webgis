# 遥感三维地球平台

数据源可插拔的遥感 WebGIS。统一目录，在三维地球上加载影像、地形和 3D Tiles，并做时序对比。

## 自定义 XYZ

`custom_xyz` 是引用型插件。用户填写自己有权使用的瓦片 URL 模板即可接入，不必再写插件代码。模板需要包含级别和行列，例如 `{z}/{x}/{y}`，需要多时相时再加 `{time}`。

这个插件不内置任何第三方地图地址，也不提供「打开地图官网、用浏览器解析瓦片 URL」的功能。那种做法可能违反数据方的服务条款。只填写你已获授权的地址。

天地图、吉林一号、四维地球、世纪空间、腾讯地图、谷歌地图都不通过抓取瓦片接入。有官方接口的，只在你自己申请的 Key 下按官方方式引用；没有授权的保持骨架。腾讯地图是 GCJ-02 电子地图，不会直接叠到 WGS84 地球上。

演示用公开数据：Sentinel-2 / Landsat 公开 STAC、NASA GIBS、Cesium ion、ArcGIS Wayback，以及 OpenStreetMap 底图。条款和额度以各官网当前说明为准。

## 添加图层

点「图层」弹出能铺到地球的源，不再单独放一块数据源列表。NASA GIBS 和 ArcGIS Wayback 直接给出 `{z}/{x}/{y}`。公开 STAC 要先填地图范围。有时间维的源才选时间，默认是该源的最近一景；没有时间维的跳过。确认后铺到三维地球。底图和地形来自地球配置，不在这个弹层里。需要密钥、尚未实现、或不提供瓦片的来源不会出现。已经挂上的图层行仍可显隐、调透明度和删除。

## 启动

一条命令起默认三容器：PostGIS、API、网关。网关同时是浏览器入口和前端静态宿主，
所以打开 <http://localhost:8080> 就能用。

```
docker compose up
python scripts/smoke.py
```

`scripts/smoke.py` 会走一遍真实链路：静态页面 → 目录 API → 上传一景 GeoTIFF →
入库出 COG → 取瓦片 → 取 WMTS capabilities → 采样切片耗时。它不需要 Docker 以外
的任何东西，仓库里也不带二进制测试数据（影像现场造）。

**开发期**分别起目录 API 和前端，切片路由同进程挂在 `/cog`：

```
cd backend
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:build --factory --reload
cd frontend && pnpm install && pnpm dev
```

开发期不需要数据库，`Settings` 默认落在 `backend/catalog.db`；上传入库要真实切片
的话装 GDAL 依赖：`pip install -e ".[dev,gdal,postgres]"`。

**表结构只有迁移这一条路。** 启动时如果库里的 alembic 版本落后于代码 head，
API 会直接拒绝启动而不是带着漂移跑。`backend/alembic.ini` 里的 URL 来自
`WEBGIS_DATABASE_URL`，别再往 ini 里写死地址。

**地址约定**：目录 API 在 `/api/*`（网关剥掉前缀），切片与 WMTS 在 `/cog/*`
（前缀原样透传）。两种前缀并存是有意的——切片服务不是目录 API 的一部分。

## 对外服务

入库后的 COG 通过默认切片服务同时给出三套地址，服务三类不同消费者：

| 地址 | 消费者 | 说明 |
| --- | --- | --- |
| `/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=<cog>` | Cesium、QGIS 的 XYZ 瓦片源 | 动态切片，无状态 |
| `/cog/WMTSCapabilities.xml?url=<cog>&use_epsg=true` | ArcGIS Pro、任何按 OGC 读文档的客户端 | `use_epsg=true` 让 `SupportedCRS` 写成 `EPSG:3857` 而不是 URN，这是 Pro 能直接添加的关键 |
| `/cog/preview?url=<cog>` | 单幅覆盖 | 渲染成一张图 |

`url=` 参数直接交给 GDAL 打开，所以默认只放行 `WEBGIS_DATA_DIR` 之下的本地
GeoTIFF；远程地址需要运维在 `WEBGIS_REMOTE_COG_HOSTS` 里显式列出主机。挡住
`../` 穿越、软链逃逸、`file://` 与未放行主机。

`GET /api/tiles/timing` 会真的发一次请求来测耗时，并如实说明有没有缓存层。
没缓存层时报 `cache: "none"`，装了缓存层也只报 `"unverified"`——命中率要从缓存层
自己的日志读，不在这个端点里假设。

GeoServer、Redis、MinIO 不在默认路径里。
