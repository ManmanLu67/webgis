# 实现计划：目录核心与数据源契约

**分支**: `001-catalog-provider` | **日期**: 2026-09-28 | **规格**: [spec.md](./spec.md)

**输入**: 来自 `/specs/001-catalog-provider/spec.md` 的功能规格

## 摘要

管理员登记数据源，并按地点、时间和云量检索影像。开发者新增一个 `plugins/<id>/` 包，重启后在 `GET /providers` 看到它，目录核心零改动。引用型与入库型条目共用一份图层文档。损坏的 `plugin.yaml` 只失败该包。本功能里切片发布只是接口；COG 转换属于 Spec 002。

## 技术上下文

**语言/版本**: Python 3.12

**主要依赖**: FastAPI、SQLAlchemy 2、GeoAlchemy2、Alembic、pystac、Pydantic v2、PyYAML。测试使用 pytest 和 httpx。本功能不引入 TiTiler、Redis 或 GeoServer。

**存储**: Compose 中使用 PostgreSQL + PostGIS。自动化测试使用 SQLite 加数值范围列，因此不依赖 Docker。仅当数据库方言为 PostgreSQL 时，Alembic 才增加 PostGIS `geometry` 列。

**测试**: pytest。覆盖插件加载、条目检索、共用图层形状和发布器切换。

**目标平台**: Linux 容器（API）以及运行 pytest 的开发机。Docker Compose 服务为 `api` 与 `postgis`。`web` 服务在 Spec 003 加入。本功能默认两个服务，仍在三容器上限之内（C7）。

**项目类型**: Web 服务（本功能仅 API）

**性能目标**: 演示数据集上的目录检索在 1 秒内返回（SC-001）。本功能不考核瓦片延迟。

**约束**: 核心只依赖 `DataSourceProvider` 与 `TilePublisher`（C1）。STAC 条目由 `pystac` 生成，禁止手写 JSON（C2）。云量未知时不通过云量过滤。跨日期变更线的矩形返回明确错误，不得静默对调。本阶段尚不需要 GDAL。

**规模/范围**: 一名管理员，数十个数据源，数千条条目。无认证。

## 宪章检查

*门禁：阶段 0 研究之前必须通过。阶段 1 设计之后再查一次。*

| 门禁 | 结果 |
|---|---|
| C1 契约 | 通过。核心只导入协议。厂商代码留在 `plugins/`。 |
| C2 标准 | 通过。条目用 `pystac` 序列化。无私有瓦片协议。不声称提供 WMS。 |
| C3 双接入 | 通过。引用与入库共用一个 `Layer` 结构。 |
| C4 合规 | 通过。加载器记录清单中的 `license_note` 与 `cache_allowed`。不猜测商业接口。 |
| C5 解耦 | 通过。使用 `ProviderRegistry` 与 `TilePublisherRegistry`。无地球代码。 |
| C6 可演示 | 通过。`GET /providers` 与 `GET /items` 可录屏。 |
| C7 作品集 | 通过。无 GeoServer、Redis、MinIO。Compose 不超过三个服务。 |
| C8 性能 | 不适用于瓦片计时。检索目标见上文。 |

设计后复查：结果相同。没有需要辩护的违规。

## 项目结构

### 本功能文档

```text
specs/001-catalog-provider/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── catalog.openapi.yaml
└── tasks.md
```

### 源代码（仓库根目录）

```text
backend/
├── pyproject.toml
├── alembic.ini
├── alembic/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── plugins/loader.py
│   ├── providers/protocol.py
│   ├── publishers/protocol.py
│   ├── publishers/registry.py
│   ├── catalog/search.py
│   ├── catalog/stac.py
│   └── api/routes.py
├── tests/
│   ├── test_plugins.py
│   ├── test_items.py
│   └── test_layers.py
└── plugins/
    └── sample_reference/
docker-compose.yml
```

**结构决定**: API 放在 `backend/`。插件放在 `backend/plugins/`，使同一个包根既能导入 `app` 也能导入插件模块。本功能不创建 Vue 应用。

## 复杂度追踪

> 无宪章违规。
