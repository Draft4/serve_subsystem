# 输入输出接口

提供 `/tennis/serve/create_job`、`get_job`、`job_command`、`job_heartbeat`；消费 `/tennis/serve/plan_shot`、`model_info`、`set_launcher_hold`、`execute_shot`；发布 `/tennis/serve_status`。

| 接口名 | 类型 | 生产/消费方 | 单位、坐标、时间与超时约定 |
| --- | --- | --- | --- |
| `/tennis/serve/create_job` 等四项 | ROS Service | operator → mission | 任务 ID 与步骤；按请求响应 |
| `/tennis/serve/plan_shot` | `PlanShot` 客户端 | mission → launcher planner | 目标为场地绝对坐标 m |
| `/tennis/serve/execute_shot` | `ExecuteShot` 客户端 | mission → supervisor | 单球目标、状态反馈、取消 |
| `/tennis/serve/set_launcher_hold` | `SetLauncherHold` 客户端 | mission → supervisor | 运行时约 0.25 s 续租 |
| `/tennis/serve_status` | `ServeSystemStatus` 话题 | mission → operator | 10 Hz、默认 depth 10；状态时间戳见消息 |
| `/localization/robot_state`、`/tennis/launcher/state` | 状态话题 | 外部 → mission | 状态年龄上限默认 1 s |

ROS 接口若未单列 QoS，则使用对应节点源码中的 `create_*` 配置；
消息头时间戳和 `valid_until` 以接口字段为准。跨包接口字段的权威定义位于
`tennis_serve_interfaces` 的 `msg/`、`srv/`、`action/`，外部硬件字段以
`tennisbot_launcher` 实际消息定义为准。更改类型、单位、坐标或超时约定时，
须与生产方及消费方共同确认。
