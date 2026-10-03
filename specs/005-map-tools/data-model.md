# 数据模型：图层管理与工具

## 标注（`annotation`）

| 字段 | 规则 |
|---|---|
| id | 字符串，必填，唯一 |
| geometry_json | GeoJSON 几何，类型只能是 Point、LineString、Polygon |
| properties_json | 对象，默认 `{}` |
| created_at | 时间戳，必填 |

线至少两个位置。面的外环至少四个位置（含闭合点）。点至少有经度和纬度。

PostgreSQL 上另有 `geometry` 列，由几何文本生成。SQLite 不建该列。

## 图层项（仅页面）

| 字段 | 规则 |
|---|---|
| id | 字符串 |
| name | 字符串 |
| group | 数据源分组名 |
| visible | 布尔 |
| opacity | 0..1 |
| order | 整数，小的在上 |

## 书签（仅浏览器）

| 字段 | 规则 |
|---|---|
| name | 字符串，必填 |
| lon | -180..180 |
| lat | -90..90 |
| height | 米，默认 1500000 |
