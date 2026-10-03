# 任务：时序卷帘

**输入**: `/specs/004-time-swipe/` 中的设计文档

**前提**: plan.md、spec.md、research.md、data-model.md

**测试**: 分割数学和来源列表用 vitest。拖动手感用浏览器。

## 阶段 1：用户故事 1 - 拖动分隔条（优先级：P1）

- [x] T001 [P] [US1] 在 `frontend/src/map/swipe.ts` 放时相列表、`clampSplit` 和 `splitFromPointer`
- [x] T002 [P] [US1] 在 `frontend/src/map/swipe.test.ts` 覆盖夹取、指针换算和三种来源
- [x] T003 [US1] 在 `frontend/src/map/layerTypeRegistry.ts` 的图层句柄上增加左右分割和移除
- [x] T004 [US1] 在 `frontend/src/map/cesiumLayers.ts` 为影像设置左右分割
- [x] T005 [US1] 在 `frontend/src/map/globe.ts` 挂载左右影像并只更新分割位置
- [x] T006 [US1] 在 `frontend/src/App.vue` 增加卷帘开关和可拖动分隔条

## 阶段 2：用户故事 2 - 独立切换时间（优先级：P1）

- [x] T007 [US2] 在 `frontend/src/App.vue` 为左右各放一个时间选择，更换时只重挂那一侧

## 阶段 3：用户故事 3 - 三种来源（优先级：P2）

- [x] T008 [US3] 选项文字带来源名称，署名使用该时相自己的说明

## 阶段 4：收尾

- [x] T009 运行卷帘单测，并在浏览器拖动分隔条、切换一侧时间

## 依赖

T001 → T005 → T006。T007 依赖 T006。T002 只依赖 T001。

## 实现策略

最小可用是打开卷帘并拖动。左右换时间和三种来源标签接着做。

- 2026-09-28：前端测试 7 项通过。浏览器勾选卷帘后左右影像不同，帧率 60。右侧改成历史版本时，左侧仍是本地入库。分隔条的指针换算由单测覆盖。
