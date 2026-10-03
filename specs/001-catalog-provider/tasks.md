# 任务：目录核心与数据源契约

**输入**: `/specs/001-catalog-provider/` 中的设计文档

**前提**: plan.md、spec.md、research.md、data-model.md、contracts/catalog.openapi.yaml、quickstart.md

**测试**: 包含。宪章技术约束要求对数据源契约和目录检索做自动化检查。

**组织**: 任务按用户故事分组。

## 格式：`[ID] [P?] [故事] 描述`

## 阶段 1：搭建（共享基础设施）

**目的**: API 项目骨架

- [x] T001 创建 `backend/pyproject.toml`，包含 FastAPI、SQLAlchemy、Alembic、pystac、PyYAML、pytest
- [x] T002 [P] 添加 `backend/app/__init__.py` 以及包目录 `backend/app/plugins`、`backend/app/providers`、`backend/app/publishers`、`backend/app/catalog`、`backend/app/api`
- [x] T003 [P] 在 `backend/pyproject.toml` 中配置 ruff

## 阶段 2：基础（阻塞前提）

**目的**: 数据库和应用工厂。未完成前不能做任何故事。

- [x] T004 在 `backend/app/config.py` 增加设置（`database_url`、`plugins_dir`、`default_publisher`）
- [x] T005 在 `backend/app/db.py` 增加引擎和会话工厂（默认 SQLite，接受 PostgreSQL 地址）
- [x] T006 在 `backend/app/models.py` 增加 `Provider`、`Collection`、`Item`、`Layer`，含范围列及数据模型约束（`minx <= maxx`，模式枚举 `reference|ingest`，云量为空或 0..100）
- [x] T007 在 `backend/alembic.ini` 和 `backend/alembic/` 搭建 Alembic，仅 PostgreSQL 方言增加 PostGIS 几何列
- [x] T008 在 `backend/app/main.py` 增加 `create_app`，建表并挂载路由

**检查点**: 应用能启动并创建空目录。

## 阶段 3：用户故事 1 - 检索已登记影像（优先级：P1）

**目标**: 按地点、时间和云量过滤条目，输出 STAC 集合。

**独立测试**: 植入两条条目后，`GET /items` 只返回匹配项，包括空列表。

- [x] T009 [P] [US1] 在 `backend/tests/test_items.py` 增加检索测试，覆盖范围、时间、`cloud_cover_lt`、空云量和空结果
- [x] T010 [US1] 在 `backend/app/catalog/search.py` 实现范围、时间和云量过滤（排除空云量；跨日期变更线 `min_lon > max_lon` 抛出明确错误）
- [x] T011 [US1] 在 `backend/app/catalog/stac.py` 用 pystac 序列化结果
- [x] T012 [US1] 按 `contracts/catalog.openapi.yaml` 在 `backend/app/api/routes.py` 增加 `GET /items`

**检查点**: 没有插件时用户故事 1 的检索也能工作。

## 阶段 4：用户故事 2 - 不改核心即可新增数据源（优先级：P1）

**目标**: 放入 `plugin.yaml` 包后出现在 `GET /providers`。坏清单指出缺失字段且不挡住其他包。

**独立测试**: 临时插件目录加一份损坏清单。

- [x] T013 [P] [US2] 在 `backend/tests/test_plugins.py` 增加插件测试
- [x] T014 [US2] 在 `backend/app/providers/protocol.py` 增加 `DataSourceProvider` 协议
- [x] T015 [US2] 在 `backend/app/plugins/loader.py` 实现清单加载（必填键、重复标识保留第一个并写出两条路径、目录名必须与清单标识一致）
- [x] T016 [US2] 在 `backend/app/api/routes.py` 增加 `GET /providers` 和 `GET /providers/errors`
- [x] T017 [US2] 增加示例包 `backend/plugins/sample_reference/`，加载器导入它时不修改 `backend/app/`

**检查点**: 新文件夹在重启后出现；坏文件夹不会卸掉示例包。

## 阶段 5：用户故事 3 - 一种图层描述（优先级：P2）

**目标**: 引用与入库条目共用一份图层文档。切换发布器不在目录里写分支。

**独立测试**: 两条条目、两个发布器标识、相同 JSON 字段，`backend/app/catalog/` 内没有发布器名字。

- [x] T018 [P] [US3] 在 `backend/tests/test_layers.py` 增加图层测试
- [x] T019 [US3] 在 `backend/app/publishers/protocol.py` 和 `backend/app/publishers/registry.py` 增加 `TilePublisher` 与注册表
- [x] T020 [US3] 在 `backend/app/api/routes.py` 增加 `GET /items/{item_id}/layer`，只通过注册表调用
- [x] T021 [US3] 增加示例入库包 `backend/plugins/sample_ingest/`

**检查点**: 两种接入模式都返回 `type`、`url`、`style`、`time_dimension`。

## 阶段 6：收尾

- [x] T022 增加只含 `postgis` 和 `api` 的 `docker-compose.yml`，以及 `backend/Dockerfile`
- [x] T023 运行 `backend` 的 pytest，并把结果记在本文件备注中

## 依赖与执行顺序

- 搭建 → 基础 → US1 → US2 → US3 → 收尾
- US2 和 US3 都需要应用工厂。US3 需要 US1 的条目。US2 可以用空条目表测试。

## 并行示例：用户故事 1

```text
T009 tests/test_items.py
T006 models.py（已在基础阶段）
```

## 实现策略

最小可用是用户故事 1（`GET /items`）。US2 证明插件主张。US3 在 Spec 002 做真瓦片之前证明共用图层形状。

## 备注

- 仓库当时还没有代码，测试与实现同一轮写出；过滤或加载规则回退时测试必须失败。
- 2026-09-28：`backend` pytest 7 项通过；ruff 干净。
