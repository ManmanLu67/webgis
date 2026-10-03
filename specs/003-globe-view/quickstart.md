# 快速验证：三维地球

## 检查

```text
cd frontend
pnpm install
pnpm test
pnpm dev
```

浏览器打开开发服务器地址。

预期：

- 不设置 `VITE_ION_TOKEN` 时，地球上有全球影像，署名含 OpenStreetMap，地形说明为椭球。
- 影像、地形可以各自开关。影像透明度可以调低。
- 未配置三维瓦片时，该项标明未配置，影像仍然可见。
- 帧率数字大于 0。

有 ion 令牌时，在 `frontend/.env.local` 写入 `VITE_ION_TOKEN`，不要把令牌提交进仓库。
