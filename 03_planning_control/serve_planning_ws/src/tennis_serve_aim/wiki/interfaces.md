# 输入输出接口

提供 `/tennis/serve/plan_aim` (`PlanAim`)；输入 request_id、CourtTarget、机器人当前 X/Y 米；输出目标 yaw 弧度。

| 接口名 | 类型 | 生产/消费方 | 单位、坐标、时间与超时约定 |
| --- | --- | --- | --- |
| `/tennis/serve/plan_aim` | `PlanAim` Service | launcher planner → aim | `robot_x_m`/`robot_y_m` 为 `court_origin_v2` 米；`target_yaw_rad` 为 0 指向 +Y、逆时针为正 |

ROS 接口若未单列 QoS，则使用对应节点源码中的 `create_*` 配置；
消息头时间戳和 `valid_until` 以接口字段为准。跨包接口字段的权威定义位于
`tennis_serve_interfaces` 的 `msg/`、`srv/`、`action/`，外部硬件字段以
`tennisbot_launcher` 实际消息定义为准。更改类型、单位、坐标或超时约定时，
须与生产方及消费方共同确认。
