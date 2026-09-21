# 模块与主要函数

`ServePlannerNode._robot_callback`：缓存定位；`_plan`：新鲜度与模型规划；`ModelService`：加载快照和参数推断；`launcher_strategy/`：策略实现。

输入输出与异常：提供 `/tennis/serve/plan_shot` (`PlanShot`) 和 `/tennis/serve/model_info` (`GetModelInfo`)；消费 `/tennis/serve/plan_aim`、`/localization/robot_state`。

| 方法 | 输入 → 输出 | 异常与边界 |
| --- | --- | --- |
| `_robot_callback` | `RobotState` → 定位快照 | 数据长度、数值或时间无效时丢弃 |
| `_plan` | `PlanShot.Request` → `PlannedShot` | 定位过期、Aim 服务不可用或模型拒绝时返回错误码 |
| `_shot_message` | 模型结果与 yaw → `PlannedShot` | 统一写入接口版本、场地坐标和模型版本 |
| `ModelService.metadata` | 模型快照 → 模型元数据 | 快照缺失或格式无效时抛 `ModelError` |
| `ModelService.plan` | 请求 ID、目标、定位 → RPM/俯仰和落点统计 | 模型边界与候选约束不满足时抛 `ModelError` |
