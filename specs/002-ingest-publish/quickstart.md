# 快速验证：入库

## 检查

```text
cd backend
pytest tests/test_jobs.py
```

预期：

- 上传返回状态 `queued`。
- 用测试转换器调用 `run_once` 得到 `success`、一条条目和一个图层 URL。
- 留在 `running` 的任务经过 `recover_interrupted` 后为 `failed`，且没有条目。
- 同一地点两个日期的上传能被 `datetime` 分开。
- `GET /tiles/timing` 包含 `duration_ms`，且 `cache` 为 `none`。

## 运行

在 API 容器上设置 `WEBGIS_WORKER_ENABLED=true`。不要增加工作进程服务。宿主机不需要 GDAL；API 镜像安装 rasterio。
