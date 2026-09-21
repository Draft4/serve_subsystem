# 模块与主要函数

`localization_to_court_xy`：定位坐标；`target_yaw_from_court_delta`：目标朝向；`validate_absolute_target`：目标区校验；`RobotSample`：定位快照。

输入输出与异常：Python 函数接口：输入场地坐标米、角度弧度，返回经校验的数值或抛出 `ValueError`。不创建 ROS topic/service。

| 函数/类 | 输入 → 输出 | 异常与边界 |
| --- | --- | --- |
| `localization_to_court_xy` | 定位 X/Y（m）→ 场地 X/Y（m） | 非有限数值拒绝 |
| `target_yaw_from_court_delta` | 目标相对位移 X/Y（m）→ yaw（rad） | 调用方先校验目标；本函数不单独拒绝零向量 |
| `validate_absolute_target` | `CourtTarget` → 无返回 | 越界或非法尺寸抛 `ValueError` |
| `observation_received_monotonic` | 当前单调时钟和观测年龄（s）→ 接收时间（s） | 非有限年龄拒绝；负年龄按 0 处理 |
| `RobotSample` | 位置、姿态、速度、新鲜度 → 定位快照 | 是否有效由调用方判定 |
