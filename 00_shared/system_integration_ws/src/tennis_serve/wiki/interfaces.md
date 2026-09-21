# 输入输出接口

提供 `ros2 launch tennis_serve tennis_serve.launch.py` 启动入口；不定义新的消息或服务。运行中的 ROS 接口详见各功能包。

| 接口名 | 类型 | 生产/消费方 | 单位、坐标、时间与超时约定 |
| --- | --- | --- | --- |
| `tennis_serve.launch.py` | ROS launch | systemd / 操作员 → 五个节点 | 启动时加载各包 YAML；无坐标或时间戳 |
| `tennis-serve.service` | systemd | 系统 → launch | 依赖工作空间环境和 `TENNIS_API_TOKEN` 环境文件 |

ROS 接口若未单列 QoS，则使用对应节点源码中的 `create_*` 配置；
消息头时间戳和 `valid_until` 以接口字段为准。跨包接口字段的权威定义位于
`tennis_serve_interfaces` 的 `msg/`、`srv/`、`action/`，外部硬件字段以
`tennisbot_launcher` 实际消息定义为准。更改类型、单位、坐标或超时约定时，
须与生产方及消费方共同确认。
