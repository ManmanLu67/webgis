# 实现计划：三维地球视图

**分支**: `003-globe-view` | **日期**: 2026-09-28 | **规格**: [spec.md](./spec.md)

**输入**: 来自 `/specs/003-globe-view/spec.md` 的功能规格

## 摘要

用 Vite + Vue 3 + TypeScript + CesiumJS 提供可浏览的全球地球。影像、地形、三维瓦片由 `LayerTypeRegistry` 创建。视图核心只调用注册表，不按厂商分支。底图和地形地址来自环境配置；没有 Cesium ion 令牌时使用公开影像和椭球地形，并显示署名。画面展示帧率。

## 技术上下文

**语言/版本**: TypeScript 5，Vue 3，Vite，CesiumJS

**主要依赖**: `vue`、`cesium`、`vite-plugin-cesium`。测试用 vitest，只覆盖注册表纯函数。

**存储**: 无。视图配置来自 `VITE_*` 环境变量。

**测试**: `pnpm test` 运行注册表单测。地球交互用浏览器手工验证。

**目标平台**: 开发期 Vite。Compose 增加 `web` 服务后，默认路径为 postgis + api + web（C7）。

**项目类型**: Web 应用前端

**性能目标**: 启动后能读到大于 0 的帧率。30fps 预算留到实测，本功能先把读数显示出来（C8）。

**约束**: ion 地址只出现在 Cesium 适配器里，形式为 `ion://<资产号>`，由配置解析器决定是否使用（C5、C6）。未知图层类型抛错且不改已加载图层。地形同时只有一个提供者。

**规模/范围**: 一个地球视图，三类图层，一个署名条。

## 宪章检查

| 门禁 | 结果 |
|---|---|
| C1 | 通过。前端不出现数据源厂商分支。 |
| C2 | 通过。图层类型是 xyz、wmts、cog、terrain、3dtiles。 |
| C3 | 通过。视图只认图层类型和地址。 |
| C4 | 通过。无令牌时不调用 ion。署名写明数据来源。OSM 瓦片仅作无令牌时的公开底图。 |
| C5 | 通过。`LayerTypeRegistry` 创建图层。视图核心无类型分支。 |
| C6 | 通过。打开页面即可浏览。 |
| C7 | 通过。不引入 React。不增加 GeoServer。 |
| C8 | 通过。帧率可见。不把未测量的 30fps 写成已达标。 |

设计后复查：无违规。

## 项目结构

### 本功能文档

```text
specs/003-globe-view/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/globe.md
└── tasks.md
```

### 源代码

```text
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── src/main.ts
├── src/App.vue
├── src/config.ts
├── src/map/layerTypeRegistry.ts
├── src/map/cesiumLayers.ts
├── src/map/globe.ts
└── src/map/layerTypeRegistry.test.ts
```

**结构决定**: `globe.ts` 只挂载注册表返回的图层。Cesium 与 `ion://` 留在 `cesiumLayers.ts`。

## 复杂度追踪

> 无宪章违规。
