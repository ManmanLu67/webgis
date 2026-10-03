# 研究：入库、发布与缓存

## 决定：工作线程放在 API 进程内

- **决定**: `WEBGIS_WORKER_ENABLED=true` 时启动守护线程轮询 `job` 表。测试关闭它，直接调用 `run_once`。
- **理由**: 宪章禁止用 `BackgroundTasks` 做分钟级工作，也禁止默认路径上的 Redis 容器。`web` 出现后再加独立工作服务就会变成第四个容器，破坏 C7。
- **考虑过的替代**: FastAPI `BackgroundTasks`（重启即丢）。Celery/Redis（只属于可选 profile，现在不上）。Compose 的 `worker` 服务（多一个容器）。

## 决定：用状态更新领取任务

- **决定**: `run_once` 选出最老的 `queued` 行，设为 `running` 并提交，然后再转换。下一次调用不会再把该行看成排队。
- **理由**: 规格边界：同一任务不得跑两次。
- **考虑过的替代**: `SELECT FOR UPDATE`（SQLite 测试不能依赖它）。内存队列（重启即丢）。

## 决定：启动时把中断任务标为失败

- **决定**: 循环开始前，每条 `running` 任务变为 `failed`，消息为「interrupted by process restart」。
- **理由**: FR-005。留在 `running` 会掩盖已经死掉的工作进程。
- **考虑过的替代**: 原地续跑（进程死在写文件中途不安全）。删除任务（规格禁止消失）。

## 决定：测试转换器复制字节；镜像内用 rasterio

- **决定**: 接缝是 `CogConverter.to_cog`。测试注入一个复制文件并返回范围与时间的转换器。能导入 rasterio 时使用 `RasterioCogConverter`。Docker 镜像安装 rasterio。宿主机 pytest 不需要 GDAL。
- **理由**: 总纲要求不在宿主机安装 GDAL。测试仍必须证明任务状态机。
- **考虑过的替代**: 等 Docker 再测入库。在宿主机调用 `gdal_translate`。

## 决定：没有缓存时的瓦片计时

- **决定**: `GET /tiles/timing` 返回毫秒时长和 `cache: "none"`。它暂时不代理真正的 COG 瓦片。
- **理由**: C8 禁止在没有缓存时报告命中。以后换成真实 TiTiler 代理时，不必改这个标签规则。
- **考虑过的替代**: 在没有 GWC 时报告 GWC 命中。
