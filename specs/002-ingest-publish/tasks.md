# 任务：入库、发布与缓存

**输入**: `/specs/002-ingest-publish/` 中的设计文档

**前提**: plan.md、spec.md、research.md、data-model.md、contracts/jobs.openapi.yaml

**测试**: 包含。宪章要求自动化覆盖从入库到瓦片 URL。

## 阶段 1：基础

- [x] T001 在 `backend/app/models.py` 增加 `Job`，状态枚举 `queued|running|success|failed`，进度 0..1，可空错误，`payload_json`、`created_at`、`updated_at`
- [x] T002 增加 Alembic 修订 `backend/alembic/versions/0002_job.py`
- [x] T003 在 `backend/pyproject.toml` 增加 `fsspec`，在 `backend/Dockerfile` 的镜像安装中增加 `rasterio`

## 阶段 2：用户故事 1 - 上传后成为可加载影像（优先级：P1）

**独立测试**: 上传，跑一个任务，读到图层 URL。重启恢复不创建条目。

- [x] T004 [P] [US1] 在 `backend/tests/test_jobs.py` 增加排队、成功、重复领取和中断恢复的测试
- [x] T005 [US1] 在 `backend/app/ingest/converter.py` 增加 `CogConverter` 和复制转换器
- [x] T006 [US1] 在 `backend/app/ingest/worker.py` 增加 `recover_interrupted` 和 `run_once`
- [x] T007 [US1] 在 `backend/app/api/routes.py` 增加 `POST /jobs/uploads` 和 `GET /jobs/{job_id}`
- [x] T008 [US1] 仅当 `WEBGIS_WORKER_ENABLED` 为真时，在恢复之后从 `backend/app/main.py` 启动工作线程

## 阶段 3：用户故事 2 - 区分时间（优先级：P2）

**独立测试**: 两次上传，一次时间过滤，一条要素。

- [x] T009 [US2] 在 `backend/app/ingest/worker.py` 把上传的 `acquired_at` 写到条目上
- [x] T010 [US2] 扩展 `backend/tests/test_jobs.py`，使同一地点的两个时间不会一起返回

## 阶段 4：用户故事 3 - 状态与瓦片计时（优先级：P2）

**独立测试**: 失败任务带有错误。计时 JSON 有时长且 `cache=none`。

- [x] T011 [US3] 转换器抛错时在 `backend/app/ingest/worker.py` 把任务标为失败，且不创建条目
- [x] T012 [US3] 在 `backend/app/api/routes.py` 增加 `GET /tiles/timing`，返回 `duration_ms` 和 `cache: none`

## 阶段 5：收尾

- [x] T013 在 `docker-compose.yml` 的 `api` 服务上设置 `WEBGIS_WORKER_ENABLED=true`
- [x] T014 运行 pytest 并把结果记在本文件

## 依赖

T001 → T006 → T007。T012 不依赖转换。US2 依赖 US1 创建条目。

## 实现策略

最小可用是一次成功上传和一个图层 URL（US1）。时间过滤和计时随后。

- 2026-09-28：`backend` pytest 13 项通过。宿主机测试使用 `CopyConverter`。真正的 COG 转换是镜像内的 `RasterioCogConverter`，本机未执行。
