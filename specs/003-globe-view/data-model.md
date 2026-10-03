# 数据模型：地球视图

本功能不新增数据库表。视图状态在页面内。

## 图层描述

| 字段 | 规则 |
|---|---|
| id | 字符串，必填 |
| type | `xyz`、`wmts`、`cog`、`terrain`、`3dtiles` 之一 |
| url | 字符串，必填。空的三维瓦片地址表示未配置 |
| opacity | 数字 0..1，默认 1。只对影像类有意义 |
| show | 布尔，默认 true |
| maximumScreenSpaceError | 数字，仅三维瓦片，默认 16 |
| attribution | 字符串，显示在署名条 |

## 视图配置

| 字段 | 规则 |
|---|---|
| ionToken | 可空。空则不使用 ion 地址 |
| imagery | 一条影像图层描述 |
| terrain | 一条地形图层描述。同一时刻只有这一条 |
| tileset | 一条三维瓦片描述，url 可空 |

未知 `type` 必须拒绝，且不得移除已经挂上的图层。
