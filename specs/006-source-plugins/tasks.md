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

## 依赖

T001 → T002 → T004。T005 与 T006 可并行。T007 依赖两者的检索行为。T008 依赖 T005 和 T006。

## 实现策略

最小可用是数据源列表上的三种状态。样例检索随后证明公开目录和历史版本真的能产出图层地址。

- 2026-09-28：`tests/test_source_plugins.py` 与 `tests/test_plugins.py` 通过。样例检索不访问外网。默认公开目录地址未在本机对官方服务做实时检索。
- 2026-09-28：选源收到「图层」弹层。弹层只留能铺上地球的可用源。已挂上的图层行仍做显隐、透明度和删除。接口仍返回可用、需配置、未实现。
