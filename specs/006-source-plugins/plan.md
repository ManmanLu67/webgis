# 实现计划：数据源插件

**分支**: `006-source-plugins` | **日期**: 2026-09-28 | **规格**: [spec.md](./spec.md)

**输入**: 来自 `/specs/006-source-plugins/spec.md` 的功能规格

## 摘要

在 `backend/plugins/` 增加本地文件、公开 STAC、历史版本、需配置来源和两个骨架。启动时不联网。显式检索才读取远程目录，并且带上选定的时间。前端不单独放数据源列表：点「图层」只弹出能铺上地球的可用源。

## 技术上下文

**语言/版本**: 延续 Python 3.12 插件加载器

**主要依赖**: 标准库 `urllib`。不新增第三方 SDK。

**存储**: 检索结果沿用已有条目表。

**测试**: pytest 用样例响应覆盖公开目录和历史版本，并确认骨架拒绝查询、核心源码不点名这些插件。

**目标平台**: 现有 API。前端通过已有 `/api` 代理读取数据源，再在图层弹层里过滤能铺上地球的源。

**项目类型**: 插件

**性能目标**: 样例检索不访问网络，应在 2 秒内返回（SC-002）。

**约束**: 公开目录的集合编号来自插件配置，不写死波段名（C1）。历史版本 `cache_allowed: false`（C4）。骨架 `search`/`ingest` 抛出 `NotImplementedError`（C4）。

**规模/范围**: 七个插件目录。示例插件保留。

## 宪章检查

| 门禁 | 结果 |
|---|---|
| C1 | 通过。核心只按清单加载，不出现插件名分支。 |
| C2 | 通过。结果仍是目录条目和图层地址。 |
| C3 | 通过。引用型与本地文件都走同一图层结构。 |
| C4 | 通过。无授权的来源只有骨架。历史版本不另存瓦片。 |
| C5 | 通过。前端只读状态，不按厂商写加载器。 |
| C6 | 通过。接口能标出三种状态。图层弹层只用其中能铺上地球的可用源。 |
| C7 | 通过。不增加容器。 |
| C8 | 通过。启动不抓取远程影像。 |

设计后复查：无违规。

## 项目结构

```text
backend/plugins/local_file/
backend/plugins/public_stac/
backend/plugins/arcgis_wayback/
backend/plugins/gee/
backend/plugins/google_tiles/
backend/plugins/jilin1/
backend/plugins/beijing1/
backend/tests/test_source_plugins.py
```

**结构决定**: 远程读取函数可以替换，测试不访问外网。默认地址写在各插件清单里。

## 复杂度追踪

> 无宪章违规。
