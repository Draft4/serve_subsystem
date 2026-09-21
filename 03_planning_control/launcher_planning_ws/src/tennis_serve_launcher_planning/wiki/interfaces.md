# 输入输出接口

提供 `/tennis/serve/plan_shot` (`PlanShot`) 和 `/tennis/serve/model_info` (`GetModelInfo`)；消费 `/tennis/serve/plan_aim`、`/localization/robot_state`。

| 接口名 | 类型 | 生产/消费方 | 单位、坐标、时间与超时约定 |
| --- | --- | --- | --- |
| `/localization/robot_state` | `tennisbot_interfaces/RobotState` | localization → planner | `court_origin_v2`，位置 m、yaw rad；sensor data QoS，默认新鲜度 1 s |
| `/tennis/serve/plan_aim` | `PlanAim` 客户端 | planner → aim | 同一定位快照，等待服务 0.5 s、结果 1 s |
| `/tennis/serve/plan_shot` | `PlanShot` Service | mission/operator → planner | 返回 `PlannedShot`；场地坐标 m、轮速 rpm、俯仰 deg、yaw rad |
| `/tennis/serve/model_info` | `GetModelInfo` Service | operator/mission → planner | 模型版本与 SHA-256 |

ROS 接口若未单列 QoS，则使用对应节点源码中的 `create_*` 配置；
消息头时间戳和 `valid_until` 以接口字段为准。跨包接口字段的权威定义位于
`tennis_serve_interfaces` 的 `msg/`、`srv/`、`action/`，外部硬件字段以
`tennisbot_launcher` 实际消息定义为准。更改类型、单位、坐标或超时约定时，
须与生产方及消费方共同确认。
