# 任务：数据源插件

**输入**: `/specs/006-source-plugins/` 中的设计文档

**前提**: plan.md、spec.md、research.md、data-model.md

**测试**: pytest 使用样例响应。前端只展示状态。

## 阶段 1：用户故事 1 - 状态列表（优先级：P1）

- [x] T001 在 `backend/app/catalog/sync.py` 写入 `availability`，骨架或未实现的查询不影响其他插件
- [x] T002 在 `backend/app/api/routes.py` 的数据源文档中返回 `availability`
- [x] T003 [P] [US1] 增加 `backend/plugins/local_file/`、`gee/`、`google_tiles/`、`jilin1/`、`beijing1/`
- [x] T004 [US1] 在 `frontend/src/ToolsPanel.vue` 和 `frontend/src/App.vue` 列出数据源并显示可用、需配置、未实现

## 阶段 2：用户故事 2 - 检索一景（优先级：P1）

- [x] T005 [P] [US2] 增加 `backend/plugins/public_stac/`，集合和端点只来自清单
- [x] T006 [P] [US2] 增加 `backend/plugins/arcgis_wayback/`，只采用记录里已有的瓦片地址
- [x] T007 [US2] 在 `backend/app/api/routes.py` 增加显式检索，并把结果写入目录
- [x] T008 [US2] 在 `backend/tests/test_source_plugins.py` 用样例响应覆盖一景影像、历史版本和核心零改动

## 阶段 3：用户故事 3 - 骨架拒绝（优先级：P2）

- [x] T009 [US3] 确认骨架查询和入库抛出说明性的 `NotImplementedError`，并由测试固定

## 阶段 4：收尾

- [x] T010 运行插件测试。目录服务可用时，在浏览器确认未实现标记

## 阶段 5：修复「只需选时间的源被要求填范围」

- [x] T011 [US1] 在 `frontend/src/api/client.ts` 的 `searchProvider` 去掉空 bbox，不再把「没有范围」发成 `bbox: []`
- [x] T012 [US1] 在 `frontend/src/ToolsPanel.vue` 用 `undefined` 而不是 `[]` 兜底
- [x] T013 [US1] 在 `backend/app/api/routes.py` 把空数组与「没给范围」等同，与紧邻的 `tuple(bbox) if bbox else None` 对齐
- [x] T014 [P] [US1] 在 `backend/tests/test_source_plugins.py` 覆盖 GIBS/Wayback 空范围可检索，且三数/五数仍被拒
- [x] T015 [P] [US1] 在 `frontend/src/api/client.test.ts` 覆盖空 bbox 不上线、真实四元组照发

## 阶段 6：时间列表与覆盖范围

- [x] T016 [US1] 在 `backend/app/plugins/loader.py` 增加 `time_choices`（`latest` / `list`，默认 `latest`），只在 `picker: time` 时校验
- [x] T017 [US1] 在 `backend/plugins/arcgis_wayback/plugin.yaml` 声明 `time_choices: list`，其余源沿用默认
- [x] T018 [US1] 在 `backend/app/api/routes.py` 的数据源文档里返回 `time_choices`，并加契约字段与 enum 守卫测试
- [x] T019 [P] [US1] 在 `frontend/src/map/timeChoices.ts` 抽出列几条的规则并配单测；`ToolsPanel.vue` 按它取 `limit`，手填日期上移到列表之前
- [x] T020 [US1] 在 `backend/app/providers/protocol.py` 与 `catalog.openapi.yaml` 增加 `coverage_bbox`，`gibs` 声明 ±85°
- [x] T021 [US1] 在 `frontend/src/api/layerSpec.ts` 把四元组收成矩形（长度或方向不对就当没声明），`cesiumLayers.ts` 据此传 `rectangle`
- [x] T022 [US2] 在 `frontend/src/map/globe.ts` 把 `globe.baseColor` 改成接近冰雪的浅色，修掉极点露出的默认深蓝
- [x] T023 [P] [US1] 补测试：`coverage_bbox` 端到端、`time_choices` 默认与枚举、`toMountableLayer` 的矩形收窄、`loadTimes` 的 limit

## 依赖

T001 → T002 → T004。T005 与 T006 可并行。T007 依赖两者的检索行为。T008 依赖 T005 和 T006。
T011 → T012。T013 与 T011 各自独立，但两侧都要改才不会复发。
T016 → T018。T019 依赖 T018 的字段。T020 与 T021 必须成对，否则裁剪不生效。T022 与 T021 一起才好看。

## 实现策略

最小可用是数据源列表上的三种状态。样例检索随后证明公开目录和历史版本真的能产出图层地址。

- 2026-09-28：`tests/test_source_plugins.py` 与 `tests/test_plugins.py` 通过。样例检索不访问外网。默认公开目录地址未在本机对官方服务做实时检索。
- 2026-09-28：选源收到「图层」弹层。弹层只留能铺上地球的可用源。已挂上的图层行仍做显隐、透明度和删除。接口仍返回可用、需配置、未实现。
- 2026-10-04：`picker: time` 的源（GIBS、Wayback）在界面上被后端 400 挡住，实际不可用；根因是前端发 `bbox: []`、后端把空数组判成「长度不对」。两侧都改并加了回归测试，见 `docs/SPEC.md` §13 第 12 条。
- 2026-10-05：时间列表默认只列一条（历史版本源保留列表，手填日期上移为主要入口）；新增 `coverage_bbox` 修掉极地黑环，并调 `globe.baseColor` 修掉极点深蓝圆 —— 见 §13 第 14、15 条。Cesium 层的效果仍需浏览器目视，本仓库无 Cesium mock。
