# 研究：目录核心与数据源契约

## 决定：测试用 SQLite 范围列，生产用 PostGIS 几何

- **决定**: 每条条目保存 `minx`、`miny`、`maxx`、`maxy`，并用这些列做 SQL 过滤。仅当数据库方言为 PostgreSQL 时，Alembic 才增加 PostGIS `geometry` 列。
- **理由**: 宪章要求运行系统使用 PostGIS，同时要求目录自动化测试。开发者必须能在没有数据库容器时跑这些测试。
- **考虑过的替代**: 只用 GeoAlchemy 的模型（测试必须有 PostGIS）。纯内存仓储（生产路径得不到测试）。pgSTAC（宪章拒绝）。

## 决定：拒绝跨日期变更线的矩形

- **决定**: 若 `min_lon > max_lon`，返回明确错误。本功能不把矩形拆成两段。
- **理由**: 规格允许拆分或拒绝。在地球界面出现之前，拆分会使查询语义加倍。
- **考虑过的替代**: 拆成两个范围。静默环绕（已拒绝，会返回错误半球）。

## 决定：云量未知时不通过 `cloud_cover_lt`

- **决定**: 设置了云量过滤时，云量为空的条目被排除。
- **理由**: 规格边界情况。把未评分影像显示成晴空会误导管理员。
- **考虑过的替代**: 把空值当成 0。把空值当成通过。

## 决定：插件清单与入口

- **决定**: 每个包是 `backend/plugins/<id>/plugin.yaml` 加 Python 入口 `模块:类`。必填键：`id`、`name`、`version`、`mode`、`capabilities`、`credentials`、`license_note`、`cache_allowed`、`status`、`entrypoint`。`id` 必须与目录名一致。
- **理由**: 与总纲清单一致。缺一个键就指出该字段，并且只跳过该包。
- **考虑过的替代**: Setuptools 入口点（不便于直接丢一个文件夹）。JSON 清单（总纲写的是 YAML）。

## 决定：重复的数据源标识

- **决定**: 第一个有效包获胜。之后相同 `id` 的包被跳过，错误同时写出两条路径。
- **理由**: 规格边界情况。整个进程失败会让一个坏包挡住目录（违反隔离规则）。

## 决定：用 pystac 输出 STAC

- **决定**: `GET /items` 返回由 `pystac` 构建的 STAC `FeatureCollection`。
- **理由**: 宪章禁止手写 STAC JSON，也禁止 pgSTAC。
- **考虑过的替代**: 手写 GeoJSON。pgSTAC。

## 决定：TilePublisher 是接缝，不是服务器

- **决定**: 本功能交付协议和进程内注册表。默认发布器标识是 `titiler`，但只记录图层地址模板。真正的 COG 切片属于 Spec 002。
- **理由**: Spec 001 要求切换时核心不出现分支。在还没有 COG 时拉起 TiTiler，对目录故事没有帮助。
- **考虑过的替代**: 现在挂载 TiTiler（没有栅格的额外服务行为）。把 GeoServer 放进默认 Compose（违反 C7）。
