# 输入输出接口

消费 `/tennis/launcher/setpoint`、`feed_command` 与 `/launcher/*/state`；发布 `/tennis/launcher/state` 与 `/launcher/*/command`。

| 接口名 | 类型 | 生产/消费方 | 单位、坐标、时间与超时约定 |
| --- | --- | --- | --- |
| `/tennis/launcher/setpoint`、`feed_command` | `LauncherSetpoint`/`FeedCommand` | supervisor → adapter | RPM、deg；有效期与本地单调时钟双重超时 |
| `/launcher/wheels/command`、`pitch/command`、`feeder/command` | `tennisbot_launcher` 消息 | adapter → 既有硬件节点 | 轮速 rpm、俯仰 deg；命令默认 10 Hz |
| `/launcher/wheels/state`、`pitch/state`、`feeder/state` | `tennisbot_launcher` 消息 | 既有硬件节点 → adapter | 原始状态、硬件在线与拨球完成计数 |
| `/tennis/launcher/state` | `LauncherState` | adapter → supervisor/mission/operator | 默认 25 Hz；反馈有效性含真实俯仰和轮速方向 |

ROS 接口若未单列 QoS，则使用对应节点源码中的 `create_*` 配置；
消息头时间戳和 `valid_until` 以接口字段为准。跨包接口字段的权威定义位于
`tennis_serve_interfaces` 的 `msg/`、`srv/`、`action/`，外部硬件字段以
`tennisbot_launcher` 实际消息定义为准。更改类型、单位、坐标或超时约定时，
须与生产方及消费方共同确认。
