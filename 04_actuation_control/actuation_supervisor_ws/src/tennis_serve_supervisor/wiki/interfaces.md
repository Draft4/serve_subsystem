# 输入输出接口

提供 `/tennis/serve/execute_shot` Action、`/tennis/serve/set_launcher_hold` 与 `/tennis/serve/reset_emergency_stop` Service；发布底盘朝向、发球机参数和拨球命令。

| 接口名 | 类型 | 生产/消费方 | 单位、坐标、时间与超时约定 |
| --- | --- | --- | --- |
| `/tennis/serve/execute_shot` | `ExecuteShot` Action | mission → supervisor | 可取消；目标为 `PlannedShot` |
| `/tennis/serve/set_launcher_hold`、`reset_emergency_stop` | ROS Service | mission/operator → supervisor | 租约/急停锁存管理 |
| `/tennis/chassis/aim_command` | `ChassisAimCommand` 话题 | supervisor → 底盘执行方 | yaw rad，命令含有效期；下游订阅者需现场确认 |
| `/tennis/launcher/setpoint` | `LauncherSetpoint` 话题 | supervisor → adapter | rpm、deg，20 Hz 刷新；有效期默认 1 s |
| `/tennis/launcher/feed_command` | `FeedCommand` 话题 | supervisor → adapter | 每球一次，唯一 command_id 和有效期 |
| `/localization/robot_state`、`/tennis/launcher/state`、`/tennis/emergency_stop` | ROS 话题 | 外部 → supervisor | 状态默认年龄上限 0.8 s；急停锁存 |

ROS 接口若未单列 QoS，则使用对应节点源码中的 `create_*` 配置；
消息头时间戳和 `valid_until` 以接口字段为准。跨包接口字段的权威定义位于
`tennis_serve_interfaces` 的 `msg/`、`srv/`、`action/`，外部硬件字段以
`tennisbot_launcher` 实际消息定义为准。更改类型、单位、坐标或超时约定时，
须与生产方及消费方共同确认。
