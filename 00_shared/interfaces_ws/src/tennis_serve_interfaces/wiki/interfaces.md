# 输入输出接口

定义 `CourtTarget`、`PlannedShot`、`ChassisAimCommand`、`LauncherSetpoint`、`FeedCommand`、`LauncherState`、`ServeSystemStatus`、`TrainingStep`；服务 `PlanAim`、`PlanShot`、`GetModelInfo`、`CreateJob`、`GetJob`、`JobCommand`、`JobHeartbeat`、`ResetEmergencyStop`、`SetLauncherHold`；动作 `ExecuteShot`。接口类型由 `msg/`、`srv/`、`action/` 源文件确定，频率与 QoS 由生产者决定。

| 接口名 | 类型 | 生产/消费方 | 单位、坐标、时间与超时约定 |
| --- | --- | --- | --- |
| `msg/*.msg` | ROS 2 消息定义 | 各层生成/消费 | 数值字段按字段名中的 `_m`、`_rad`、`_rpm`、`_deg`；坐标见下文 |
| `srv/*.srv` | ROS 2 服务定义 | 规划、任务、执行节点 | 请求响应式；具体等待上限见调用端 |
| `action/ExecuteShot.action` | ROS 2 Action 定义 | mission → supervisor | 单球目标、反馈与结果；支持取消 |

ROS 接口若未单列 QoS，则使用对应节点源码中的 `create_*` 配置；
消息头时间戳和 `valid_until` 以接口字段为准。跨包接口字段的权威定义位于
`tennis_serve_interfaces` 的 `msg/`、`srv/`、`action/`，外部硬件字段以
`tennisbot_launcher` 实际消息定义为准。更改类型、单位、坐标或超时约定时，
须与生产方及消费方共同确认。
