# 输入输出接口

HTTP `/api/v1/health`、`status`、`model`、`plan-preview`、`recommend`、`jobs`、`jobs/{job_id}`、`jobs/{job_id}/command`、`jobs/{job_id}/heartbeat`、`emergency-stop/reset`。

| 接口名 | 类型 | 生产/消费方 | 单位、坐标、时间与超时约定 |
| --- | --- | --- | --- |
| `/api/v1/*` | HTTP/JSON | Windows 上位机 ↔ operator | 默认 0.0.0.0:8765；除 health 外使用 Bearer Token |
| `/tennis/serve/plan_shot`、`model_info`、任务服务 | ROS Service 客户端 | operator → planning/mission | 单次请求；超时默认 5 s |
| `/localization/robot_state`、`/tennis/launcher/state`、`/tennis/serve_status`、`/tennis/emergency_stop` | ROS 话题 | 外部 → operator | 默认 1 s 状态年龄门限；具体 QoS 见源码 |

ROS 接口若未单列 QoS，则使用对应节点源码中的 `create_*` 配置；
消息头时间戳和 `valid_until` 以接口字段为准。跨包接口字段的权威定义位于
`tennis_serve_interfaces` 的 `msg/`、`srv/`、`action/`，外部硬件字段以
`tennisbot_launcher` 实际消息定义为准。更改类型、单位、坐标或超时约定时，
须与生产方及消费方共同确认。
