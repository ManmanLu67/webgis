# 快速验证：时序卷帘

```text
cd frontend
node node_modules/vitest/vitest.mjs run src/map/swipe.test.ts
pnpm dev
```

浏览器打开开发服务器。

预期：

- 勾选卷帘后出现分隔条，左右影像不同。
- 拖动分隔条时帧率仍大于 0。
- 只改一侧的时间，另一侧标签不变。
- 下拉选项里能看到本地入库、公开目录、历史版本。
