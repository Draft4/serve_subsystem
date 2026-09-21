# 模块与主要函数

`ServeJobManagerNode`：服务入口与状态机；`_preflight_locked`：启动门禁；`_send_shot`：单球规划和执行；`_maintain_launcher_hold`：租约；`_publish_status`：状态。

输入输出与异常：提供 `/tennis/serve/create_job`、`get_job`、`job_command`、`job_heartbeat`；消费 `/tennis/serve/plan_shot`、`model_info`、`set_launcher_hold`、`execute_shot`；发布 `/tennis/serve_status`。

| 方法 | 输入 → 输出 | 异常与边界 |
| --- | --- | --- |
| `_validate_request`、`_create_job` | `CreateJob.Request` → 任务 ID/结果 | 限制任务步数、重复数和时间区间；拒绝非法请求 |
| `_job_command`、`_apply_command_locked` | 任务 ID、命令 → 状态转移 | 不合法状态转移返回失败 |
| `_preflight_locked` | 当前定位、机构和模型状态 → 就绪结果 | 过期或无效反馈拒绝启动 |
| `_send_shot` | 训练步骤 → `PlanShot` 与 `ExecuteShot` 结果 | 拨球前失败按配置重试；拨球后不自动重复 |
| `_maintain_launcher_hold` | 当前任务状态 → 飞轮租约 | 暂停、取消或心跳超时请求停轮 |
| `_publish_status` | 状态机和门禁 → `ServeSystemStatus` | 约 10 Hz 发布；下游仍需检查状态年龄 |
