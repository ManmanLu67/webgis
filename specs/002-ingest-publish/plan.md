# 实现计划：入库、发布与缓存

**分支**: `002-ingest-publish` | **日期**: 2026-09-28 | **规格**: [spec.md](./spec.md)

**输入**: 来自 `/specs/002-ingest-publish/spec.md` 的功能规格

## 摘要

把 GeoTIFF 上传写进 `job` 行。API 进程内的工作循环把它转成 COG，存到本地 fsspec 存储，写入 `item`，再通过已有的 `TilePublisher`（`titiler` 地址模板）发布图层。不增加 GeoServer 容器。瓦片耗时在本地端点测量，在缓存 profile 出现之前标为「无中间缓存」。

## 技术上下文

**语言/版本**: Python 3.12（延续 `backend/`）

**主要依赖**: 已有的 FastAPI 目录。增加 `fsspec`。COG 转换是 `CogConverter` 协议。测试使用复制转换器。API 镜像安装 `rasterio`，因此宿主机不需要 GDAL（C7，总纲）。

**存储**: 本地目录 `backend/data/`，经 fsspec（`file://`）。目录数据库仍是 PostGIS。测试数据库仍是 SQLite。

**测试**: pytest。任务生命周期、重启恢复、时间过滤、瓦片计时标签。

**目标平台**: 与 Spec 001 相同的 `api` 容器。`WEBGIS_WORKER_ENABLED=true` 时启动守护线程轮询，不是第四个 Compose 服务，也不是 `BackgroundTasks`。

**项目类型**: Web 服务

**性能目标**: 演示用 GeoTIFF 任务在一分钟内完成（规格假设）。瓦片计时端点返回毫秒。缓存命中预算（C8）只在真有缓存时报告。

**约束**: 默认路径没有 GeoServer（C7）。中断的 `running` 任务变为 `failed`（FR-005）。两个工作进程不得领取同一任务。非影像输入使任务失败且不创建条目。

**规模/范围**: 一名管理员，每个任务一个文件。

## 宪章检查

| 门禁 | 结果 |
|---|---|
| C1 | 通过。转换和切片留在 `CogConverter` 与 `TilePublisher` 后面。 |
| C2 | 通过。输出是 COG 加上已有的 XYZ/WMTS 风格图层地址。不声称 WMS。 |
| C3 | 通过。入库条目使用 Spec 001 的图层文档。 |
| C4 | 通过。上传文件是管理员自己的数据。 |
| C5 | 通过。无地球代码。发布器注册表不变。 |
| C6 | 通过。`POST /jobs/uploads` 与 `GET /jobs/{id}` 可录屏。 |
| C7 | 通过。不新增 Compose 服务。`rasterio` 只在镜像内。 |
| C8 | 通过。计时端点拒绝编造缓存命中。 |

设计后复查：无变化。

## 项目结构

### 本功能文档

```text
specs/002-ingest-publish/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/jobs.openapi.yaml
└── tasks.md
```

### 源代码（仓库根目录）

```text
backend/app/models.py          # 增加 Job
backend/app/ingest/converter.py
backend/app/ingest/worker.py
backend/app/api/routes.py      # 上传、读任务、瓦片计时
backend/tests/test_jobs.py
backend/Dockerfile             # 增加 rasterio
```

**结构决定**: 扩展 Spec 001 的 API。不增加工作进程容器。

## 复杂度追踪

> 无宪章违规。
