# 快速验证：目录核心

## 前提

- Python 3.12
- 在 `backend/` 中执行 `pip install -e ".[dev]"`（有锁文件后可用 `uv sync`）

自动化检查不需要 PostGIS。API 镜像存在后，运行系统是 `docker compose up postgis api`。

## 检查

```text
cd backend
pytest
```

预期：

- 额外的有效插件目录出现在 `GET /providers` 中，且没有修改 `app/` 下的文件。
- 缺少 `name` 的插件报错中包含 `name`，有效插件仍然在。
- `GET /items?bbox=&datetime=&cloud_cover_lt=` 返回 STAC FeatureCollection，并丢掉不匹配和云量未知的条目。
- 引用条目和入库条目返回字段相同的图层文档。
- 请求 `publisher=other` 会改变 `publisher_id` 和 `url`，且 `app/catalog/` 内没有分支。

## 手工

1. 带着示例插件启动 API。
2. 打开 `/providers` 和 `/items?bbox=-10,-10,10,10`。
3. 对一条已植入的引用条目和一条入库条目打开 `/items/{id}/layer`。
