# 输入输出接口

Python 函数接口：输入场地坐标米、角度弧度，返回经校验的数值或抛出 `ValueError`。不创建 ROS topic/service。

| 接口名 | 类型 | 生产/消费方 | 单位、坐标、时间与超时约定 |
| --- | --- | --- | --- |
| `localization_to_court_xy(x,y)` | Python 函数 | 定位使用方 → common | 输入/输出 m，`court_origin_v2` |
| `target_yaw_from_court_delta(dx,dy)` | Python 函数 | aim → common | 输入 m，输出 rad；0 指向 +Y |
| `validate_absolute_target(target)` | Python 函数 | 规划节点 → common | `CourtTarget`；无时间戳，非法输入抛 `ValueError` |

ROS 接口若未单列 QoS，则使用对应节点源码中的 `create_*` 配置；
消息头时间戳和 `valid_until` 以接口字段为准。跨包接口字段的权威定义位于
`tennis_serve_interfaces` 的 `msg/`、`srv/`、`action/`，外部硬件字段以
`tennisbot_launcher` 实际消息定义为准。更改类型、单位、坐标或超时约定时，
须与生产方及消费方共同确认。
