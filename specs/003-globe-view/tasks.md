# 任务：三维地球视图

**输入**: `/specs/003-globe-view/` 中的设计文档

**前提**: plan.md、spec.md、research.md、data-model.md、contracts/globe.md

**测试**: 包含注册表单测。地球画面用浏览器查看。

## 阶段 1：搭建

- [x] T001 创建 `frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json`、`frontend/index.html`（Vite、Vue 3、TypeScript、Cesium）
- [x] T002 [P] 在 `frontend/src/config.ts` 实现视图配置解析：无令牌时用公开影像和 `ellipsoid://`，有令牌且未覆盖地址时用 `ion://2` 与 `ion://1`

## 阶段 2：用户故事 1 - 打开就能浏览全球（优先级：P1）

**独立测试**: `pnpm dev` 后看到全球影像和署名。

- [x] T003 [P] [US1] 在 `frontend/src/map/layerTypeRegistry.test.ts` 覆盖登记、未知类型和透明度夹取
- [x] T004 [US1] 在 `frontend/src/map/layerTypeRegistry.ts` 实现注册表
- [x] T005 [US1] 在 `frontend/src/map/cesiumLayers.ts` 登记 xyz、wmts、cog、terrain、3dtiles，并只在此文件解释 `ion://`
- [x] T006 [US1] 在 `frontend/src/map/globe.ts` 创建地球并只通过注册表挂载图层
- [x] T007 [US1] 在 `frontend/src/App.vue` 放上地球容器和署名

## 阶段 3：用户故事 2 - 各自开关和透明度（优先级：P1）

**独立测试**: 隐藏地形不影响影像；透明度只改影像。

- [x] T008 [US2] 在 `frontend/src/App.vue` 增加影像、地形、三维瓦片的显隐，以及影像透明度
- [x] T009 [US2] 三维瓦片地址为空时，开关不可用并显示未配置

## 阶段 4：用户故事 3 - 精细度与帧率（优先级：P2）

**独立测试**: 页面上的帧率在渲染后大于 0。

- [x] T010 [US3] 在 `frontend/src/map/globe.ts` 用渲染回调更新帧率文本
- [x] T011 [US3] 在 `frontend/src/App.vue` 增加三维瓦片屏幕空间误差控件，并作用到已挂载的瓦片

## 阶段 5：收尾

- [x] T012 在 `docker-compose.yml` 增加 `web` 服务和 `frontend/Dockerfile`，使默认路径为 postgis、api、web
- [x] T013 运行 `pnpm test`，并在浏览器打开地球确认影像与署名

## 依赖

T004 → T005 → T006 → T007。T008 依赖 T007。T010 依赖 T006。

## 实现策略

最小可用是无令牌也能看到全球影像和署名。开关、透明度和帧率接着做。

- 2026-09-28：`node node_modules/vitest/vitest.mjs run` 4 项通过。浏览器打开 `http://127.0.0.1:5173/` 可见全球影像、OpenStreetMap 署名、帧率 60。三维瓦片显示未配置。`pnpm test` 在本机 pnpm 11 上会因未允许的 esbuild 构建脚本失败，已在 `pnpm-workspace.yaml` 的 `allowBuilds` 中放行。
