# 任务：图层管理与工具

**输入**: `/specs/005-map-tools/` 中的设计文档

**前提**: plan.md、spec.md、research.md、data-model.md、contracts/annotations.openapi.yaml

**测试**: 标注接口用 pytest。图层顺序、距离和坐标校验用 vitest。

## 阶段 1：用户故事 1 - 管理图层（优先级：P1）

- [x] T001 [P] [US1] 在 `frontend/src/map/layers.ts` 实现分组、移动、删除
- [x] T002 [P] [US1] 在 `frontend/src/map/layers.test.ts` 覆盖分组和到头时不移动
- [x] T003 [US1] 在 `frontend/src/ToolsPanel.vue` 列出分组图层，并接到显隐、透明度、排序、删除

## 阶段 2：用户故事 2 - 标注（优先级：P1）

- [x] T004 [P] [US2] 在 `backend/app/annotations.py` 校验点、线、面并组装 GeoJSON
- [x] T005 [US2] 在 `backend/app/models.py` 增加 `Annotation`，在 `backend/alembic/versions/0003_annotation.py` 建表
- [x] T006 [US2] 在 `backend/app/api/annotations.py` 增加列表、保存和删除，并在 `backend/app/main.py` 挂上跨源访问
- [x] T007 [US2] 在 `backend/tests/test_annotations.py` 覆盖保存、点数不够和导出
- [x] T008 [US2] 在 `frontend/src/map/globe.ts` 增加绘制和显示标注，在 `frontend/vite.config.ts` 把 `/api` 代理到目录

## 阶段 3：用户故事 3 - 量算（优先级：P2）

- [x] T009 [P] [US3] 在 `frontend/src/map/measure.ts` 实现距离、面积、高度和可复制文字
- [x] T010 [P] [US3] 在 `frontend/src/map/measure.test.ts` 核对约 1 公里的距离误差
- [x] T011 [US3] 在 `frontend/src/ToolsPanel.vue` 显示结果并复制

## 阶段 4：用户故事 4 - 飞行与书签（优先级：P2）

- [x] T012 [US4] 在 `frontend/src/map/bookmarks.ts` 校验经纬度并追加书签
- [x] T013 [US4] 在 `frontend/src/map/globe.ts` 增加飞到坐标和飞到范围
- [x] T014 [US4] 在 `frontend/src/ToolsPanel.vue` 放坐标输入、书签和飞到图层

## 阶段 5：收尾

- [x] T015 运行上述测试，并在浏览器确认图层分组和非法坐标不飞行

## 依赖

T001 → T003。T004 → T006 → T007。T008 依赖 T006 的路径，但页面在目录未启动时仍可绘制。T009 → T011。T012 → T014。

## 实现策略

最小可用是图层列表。标注、量算和飞行按故事往上加。

- 2026-09-28：标注接口 3 项通过。前端测试 12 项通过。浏览器里图层按底图、地形、本地入库、公开目录、历史版本分组。经度 200 点飞行后提示范围无效，视角不移动。目录未启动时保存标注会提示只留在本次浏览。
