# 模块与主要函数

`ServeAimNode._plan`：校验目标、转换定位、计算朝向并返回错误码。

输入输出与异常：提供 `/tennis/serve/plan_aim` (`PlanAim`)；输入 request_id、CourtTarget、机器人当前 X/Y 米；输出目标 yaw 弧度。

| 方法 | 输入 → 输出 | 异常与边界 |
| --- | --- | --- |
| `ServeAimNode._plan` | `PlanAim.Request`：目标区、当前 X/Y（m）→ yaw（rad）及状态码 | 目标无效时返回 `PLAN_REJECTED`；不更新机器人位置，也不生成路径 |
| `main` | ROS 进程参数 → 服务节点生命周期 | 节点退出时释放 ROS 资源 |
