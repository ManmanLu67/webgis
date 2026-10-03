# 快速验证：图层管理与工具

```text
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_annotations.py -q
cd ../frontend
node node_modules/vitest/vitest.mjs run src/map/layers.test.ts src/map/measure.test.ts
pnpm dev
```

浏览器打开开发服务器。预期：

- 图层按「底图」「地形」以及三种卷帘来源分组。
- 隐藏底图后地球上的影像消失。
- 画一个点后，页面上能看到该点；目录未启动时提示未写入，导出仍包含该点。
- 经度 200 不会飞行。
