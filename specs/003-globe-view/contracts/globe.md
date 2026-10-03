# 地球视图契约

## 环境变量

| 变量 | 含义 | 缺省 |
|---|---|---|
| `VITE_ION_TOKEN` | Cesium ion 访问令牌 | 空 |
| `VITE_IMAGERY_URL` | 影像地址。`ion://资产号` 或 XYZ 模板 | 有令牌时 `ion://2`，否则 OpenStreetMap 模板 |
| `VITE_IMAGERY_ATTRIBUTION` | 影像署名 | 按实际来源生成 |
| `VITE_TERRAIN_URL` | 地形地址。`ion://资产号`、量化网格 URL，或 `ellipsoid://` | 有令牌且未覆盖时 `ion://1`，否则 `ellipsoid://` |
| `VITE_TERRAIN_ATTRIBUTION` | 地形署名 | 按实际来源生成 |
| `VITE_TILESET_URL` | 三维瓦片地址，可空 | 空 |
| `VITE_TILESET_ATTRIBUTION` | 三维瓦片署名 | 空 |

## 注册表

- `registerLayerType(type, factory)` 登记一种类型。
- `createLayer(spec)` 按 `spec.type` 查找工厂。未知类型抛出包含该类型名的错误。
- `clampOpacity(value)` 把透明度限制在 0 到 1。

## 页面可读文本

- 署名区域的文本包含当前影像署名。
- 帧率区域在地球开始渲染后显示大于 0 的数字。
