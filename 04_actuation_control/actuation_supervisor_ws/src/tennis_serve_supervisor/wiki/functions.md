# 模块与主要函数

`ServeControllerNode`：Action 和服务；`gates.py`：门禁计算；`_refresh_launcher_setpoint`：租约与有效期；`_publish_launcher_stop`：停轮；`_feedback`：进度。

输入输出与异常：提供 `/tennis/serve/execute_shot` Action、`/tennis/serve/set_launcher_hold` 与 `/tennis/serve/reset_emergency_stop` Service；发布底盘朝向、发球机参数和拨球命令。

| 方法/模块 | 输入 → 输出 | 异常与边界 |
| --- | --- | --- |
| `ExecuteShot` Action 回调 | `PlannedShot` → 过程反馈和单球结果 | 可取消；急停、定位过期或门禁失败时停止 |
| `gates.py` | 定位和机构反馈、目标、阈值 → 门禁结果 | 朝向、速度、RPM、时效任一失败则拒绝拨球；不校验俯仰反馈 |
| `_refresh_launcher_setpoint` | 有效任务租约 → 周期性 setpoint | 租约过期发布停轮目标 |
| `_publish_launcher_stop` | 任务/球 ID、原因 → 停轮命令 | 失败、取消或急停时关闭输出 |
| `_feedback` | 当前阶段和门禁 → Action 反馈 | 不把参数就绪当成发球许可 |
