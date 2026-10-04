# 遥感三维地球平台

数据源可插拔的遥感 WebGIS。统一目录，在三维地球上加载影像、地形和 3D Tiles，并做时序对比。

## 架构

```
                    浏览器  http://localhost:8080
                              │
                    ┌─────────▼─────────┐
                    │  gateway (Caddy)  │  浏览器入口 + 前端静态宿主
                    └─────────┬─────────┘
              ┌───────────────┴───────────────┐
     /api/*   │ 剥掉前缀                      │ /cog/*  原样透传
    ┌─────────▼──────────┐          ┌─────────▼──────────┐
    │  api (FastAPI)     │          │  COG 切片服务      │
    │                    │◄─────────┤  （同进程，TiTiler）│
    │  目录 API          │  同一份   │                    │
    │  ProviderRegistry  │  本地文件 │  XYZ / WMTS / 预览 │
    │  TilePublisherReg. │          │                    │
    │  job worker        │          │                    │
    └─────────┬──────────┘          └─────────┬──────────┘
              │                               │
        ┌─────▼─────┐                   ┌─────▼─────┐
        │  PostGIS  │                   │ data_dir  │
        └───────────┘                   │ COG 瓦片  │
                                        └───────────┘

  plugins/<id>/{plugin.yaml, provider.py}   ── 扫描加载 ──▶  ProviderRegistry
```

两个前缀并存是有意的：**切片服务不是目录 API 的一部分**。网关对 `/api` 剥前缀、
对 `/cog` 原样透传，所以不能一刀切 `strip_prefix` —— 那样会把瓦片地址也剥掉。

切片与目录 API 同进程，因此入库 worker 写出的 COG 与切片端点读的是同一份文件，
不需要跨容器共享 volume，也不需要把本地路径改写成容器间可解析的地址。

## 自定义 XYZ

`custom_xyz` 是引用型插件。用户填写自己有权使用的瓦片 URL 模板即可接入，不必再写插件代码。模板需要包含级别和行列，例如 `{z}/{x}/{y}`，需要多时相时再加 `{time}`。

这个插件不内置任何第三方地图地址，也不提供「打开地图官网、用浏览器解析瓦片 URL」的功能。那种做法可能违反数据方的服务条款。只填写你已获授权的地址。

天地图、吉林一号、四维地球、世纪空间、腾讯地图、谷歌地图都不通过抓取瓦片接入。有官方接口的，只在你自己申请的 Key 下按官方方式引用；没有授权的保持骨架。逐个来源的授权状态与署名要求见[数据来源与署名](#数据来源与署名)。

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

## 数据来源与署名

平台不抓取违反服务条款的瓦片。每个来源的授权状态与展示要求如下 —— **展示时
署名是硬要求，不是可选项**，各家的额度与条款以官网当前说明为准。

### 公开、免认证（可演示）

| 插件 | 来源 | 署名要求 |
| --- | --- | --- |
| `public_stac` | Element 84 Earth Search 上的 Sentinel-2 L2A COG | 按该数据集官方说明标注数据集名称与提供方 |
| `gibs` | NASA GIBS / EOSDIS 全球每日影像 | 标注 NASA；平台只引用不另存瓦片 |
| `arcgis_wayback` | Esri Wayback 历史影像版本 | 标注 Esri；只登记清单里已给出的瓦片地址 |
| `local_file` | 自己上传的影像 | 无（自有数据） |
| `custom_xyz` | 用户自备地址 | 无（授权由用户自己负责） |

### 需自行申请 Key

| 插件 | 需要 | 署名与审图号 |
| --- | --- | --- |
| `tianditu` | 天地图开发者平台 Key | 展示时**必须标注审图号**，署名以天地图当前要求为准。数据基准为 CGCS2000（`EPSG:4490`），瓦片网格是标准 Web Mercator，可直接叠加 |
| `google_tiles` | Google Maps Platform API Key | 须按 Google 要求署名；只调用官方 Map Tiles API，不抓取 Google Earth 瓦片 |
| `tencent_map` | 腾讯位置服务 Key | 电子地图而非遥感影像，且为 GCJ-02 坐标系，与 WGS84 有数百米人为偏移，**不铺到地球上** |

### 怎么填 Key

变量名 = `WEBGIS_PROVIDER_SECRETS_` + 插件 id 转大写，值是一个 JSON 对象：

```bash
# backend/.env.local
WEBGIS_PROVIDER_SECRETS_TIANDITU={"tk": "你的天地图 Key"}
WEBGIS_PROVIDER_SECRETS_GOOGLE_TILES={"key": "你的 Google API Key"}
WEBGIS_PROVIDER_SECRETS_TENCENT_MAP={"key": "你的腾讯位置服务 Key"}
```

`backend/plugins/*/plugin.yaml` 里只声明需要哪些凭据的**名字**（`credentials: [tk]`），
值不进仓库 —— 这是它唯一该出现的位置。填错 JSON、漏填声明的键，都只会让**那一个源**
停在 `needs_config`，其余源照常工作（宪章 C1）。

> **⚠ 填了 Key 之后，Key 会出现在浏览器里 —— 这是躲不掉的。**
>
> 天地图是 KVP WMTS，规范要求每次瓦片请求都带 `tk`；Google 的浏览器瓦片 URL
> 同样要带 `key`。也就是说，只要图层能被浏览器加载，Key 就必然随请求下发，
> 浏览器开发者工具里看得到。靠"藏起来"是做不到的，只能靠服务方的来源限制兜底：
> **在服务方后台把 Key 限制到你的域名 / 出网 IP**（Google Cloud Console 的
> "API restrictions → Websites"，天地图的 Key 校验），并按服务方要求配好配额告警。
>
> 系统的默认是保守的：不配 Key 就不请求服务方（宪章 C4）；且带凭据的源一律
> `cache_allowed: false`，所以 Key 不会被写进任何瓦片缓存。凭据值**不会**进
> `provider` 表、不会进加载错误或日志（`tests/test_provider_secrets.py` 逐条守着）。

### 仅骨架（未接入，界面标注「未实现」）

`jilin1`、`beijing1`、`shiji`、`siwei`、`gee` —— 没有授权或没有可公开引用的接口
文档，因此只提供扩展点，不写猜测性接口。要用这些数据，走 `local_file` 自己上传。

骨架插件的存在是为了展示扩展点，不代表已对接。仓库里有守卫测试确保任何声明为
「可用」的插件都不会在 `search()` 里抛 `NotImplementedError` —— 避免界面上看起来
能用、点进去才发现不行。

### 默认底图

不配置 `VITE_*` 环境变量时，底图用 OpenStreetMap 瓦片、地形用裸椭球
（`ellipsoid://`）、3D Tiles 不加载。OSM 官方瓦片不适合大量请求；正式部署请按
[OSM 瓦片使用政策](https://operations.osmfoundation.org/policies/tiles/) 配置自己的
底图来源。
