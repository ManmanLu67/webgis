# 实现计划：图层管理与工具

**分支**: `005-map-tools` | **日期**: 2026-09-28 | **规格**: [spec.md](./spec.md)

**输入**: 来自 `/specs/005-map-tools/spec.md` 的功能规格

## 摘要

在地球旁增加工具面板：图层按数据源分组，可显隐、排序、透明度和删除。点线面画完后写入标注表，并导出 GeoJSON。距离、面积、高度用可测试的计算，结果可复制。经纬度飞行、图层范围飞行和浏览器本地书签。

## 技术上下文

**语言/版本**: 延续 FastAPI 与 Vue 3 + Cesium

**主要依赖**: 无新服务。标注表用现有数据库。PostgreSQL 上由迁移补几何列；测试仍用 SQLite 存 GeoJSON 文本。

**存储**: `annotation` 表。书签只在浏览器 `localStorage`。

**测试**: pytest 覆盖标注的保存、校验和 GeoJSON 导出。vitest 覆盖图层排序、距离和非法坐标。画面用浏览器看。

**目标平台**: 现有 `api` 与 `web`。开发期 Vite 把 `/api` 代理到 API。

**项目类型**: Web 应用

**性能目标**: 图层显隐不重建地球。

**约束**: 量算公式不放进视图核心的厂商分支（C5）。标注几何只接受点、线、面（C2 的矢量交换用 GeoJSON）。目录不可用时不假装已保存（C6）。

**规模/范围**: 一个面板，四类工具。

## 宪章检查

| 门禁 | 结果 |
|---|---|
| C1 | 通过。工具不调用某个数据源插件。 |
| C2 | 通过。导出是 GeoJSON。 |
| C3 | 通过。图层列表不按厂商分叉。 |
| C4 | 通过。不新增外部抓取。 |
| C5 | 通过。排序与量算是纯函数。绘制落在地球适配层。 |
| C6 | 通过。面板打开即可操作。 |
| C7 | 通过。不增加容器。 |
| C8 | 通过。显隐不重建地球。 |

设计后复查：无违规。

## 项目结构

```text
backend/app/annotations.py
backend/app/api/annotations.py
backend/tests/test_annotations.py
frontend/src/map/layers.ts
frontend/src/map/measure.ts
frontend/src/map/bookmarks.ts
frontend/src/ToolsPanel.vue
```

**结构决定**: 目录不可用时，标注留在当前页面并提示未写入。书签不进数据库。

## 复杂度追踪

> 无宪章违规。
