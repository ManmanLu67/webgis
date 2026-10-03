# 数据模型：任务

Spec 001 的实体保持不变。本功能增加任务。

## 任务（`job`）

| 字段 | 规则 |
|---|---|
| id | 字符串，必填，唯一 |
| type | 字符串，必填。本功能使用 `ingest` |
| status | 枚举 `queued`、`running`、`success`、`failed`，必填 |
| progress | 数字 0..1，必填，默认 0 |
| error | 字符串，可空。状态为 `failed` 时必填 |
| payload_json | 对象，必填。包含 `source_path`，成功时还有 `item_id` |
| created_at | 时间戳，必填 |
| updated_at | 时间戳，必填 |

状态迁移：`queued` → `running` → `success` 或 `failed`。启动时可以把 `running` → `failed`。没有其他迁移。

失败或中断的任务不得插入条目。

## 瓦片计时（不落库）

响应字段：`duration_ms`（数字），`cache`（在配置缓存 profile 之前为 `none`）。`cache` 为 `none` 时没有命中率字段。
