# 模块与主要函数

`ServeLauncherAdapterNode`：ROS 话题、超时和状态；`adapter_core.map_targets`：目标映射；`FeedResultTracker`：拨球结果去重与超时。

输入输出与异常：消费 `/tennis/launcher/setpoint`、`feed_command` 与 `/launcher/*/state`；发布 `/tennis/launcher/state` 与 `/launcher/*/command`。

| 方法/模块 | 输入 → 输出 | 异常与边界 |
| --- | --- | --- |
| `_setpoint_callback` | `LauncherSetpoint` → 缓存目标 | 校验有效期、RPM、俯仰与任务标识 |
| `_feed_callback` | `FeedCommand` → 待下发拨球 | 过期、重复或与当前 setpoint 不一致则拒绝 |
| `_publish_command` | 有效目标 → 底层轮速/俯仰/拨球话题 | 超时后发安全停止命令 |
| `_publish_state` | 底层反馈 → `LauncherState` | 反馈失效时标记无效 |
| `adapter_core.map_targets` | 上下轮 RPM、接线映射和符号 → 两个电机的带符号 RPM | 映射参数非法或输入 RPM 为负时抛 `ValueError`；限幅在节点层完成 |
| `FeedResultTracker` | command_id、完成计数和时间 → 拨球结果 | 去重并在默认 8 s 后超时 |
