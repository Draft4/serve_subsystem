# 模块与主要函数

`ServeBridgeNode`：ROS 客户端与状态订阅；`_target`：请求目标校验；`_status_payload`：状态整理；`_build_app`：HTTP 路由。

输入输出与异常：HTTP `/api/v1/health`、`status`、`model`、`plan-preview`、`recommend`、`jobs`、`jobs/{job_id}`、`jobs/{job_id}/command`、`jobs/{job_id}/heartbeat`、`emergency-stop/reset`。

| 方法 | 输入 → 输出 | 异常与边界 |
| --- | --- | --- |
| `_target` | HTTP 目标 JSON → `CourtTarget` | 坐标系、范围和数值非法时拒绝请求 |
| `_call` | ROS 客户端、请求、超时 → 服务响应 | 默认 5 s 超时转为 HTTP 错误 |
| `_status_payload` | 定位、机构、任务缓存 → HTTP 状态 JSON | 数据过期时标为不可用 |
| `_build_app` | FastAPI 路由注册 → HTTP 应用 | 除 health 外校验 Bearer Token |
| `start_http`、`stop_http` | 节点生命周期 → HTTP 服务生命周期 | 启动或关闭异常由节点日志报告 |
