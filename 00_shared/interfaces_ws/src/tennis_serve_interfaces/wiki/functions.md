# 模块与主要函数

msg/*.msg：状态、目标、命令；srv/*.srv：规划、任务、模型和控制服务；action/ExecuteShot.action：单球执行。

输入输出与异常：定义 `CourtTarget`、`PlannedShot`、`ChassisAimCommand`、`LauncherSetpoint`、`FeedCommand`、`LauncherState`、`ServeSystemStatus`、`TrainingStep`；服务 `PlanAim`、`PlanShot`、`GetModelInfo`、`CreateJob`、`GetJob`、`JobCommand`、`JobHeartbeat`、`ResetEmergencyStop`、`SetLauncherHold`；动作 `ExecuteShot`。接口类型由 `msg/`、`srv/`、`action/` 源文件确定，频率与 QoS 由生产者决定。

本包没有运行时类或函数；`rosidl` 在构建时根据 `msg/`、`srv/`、`action/`
生成语言绑定。字段输入、输出和约束以接口源文件为准；非法字段的业务校验
由规划、任务和执行节点完成。新增或修改字段后应重建所有依赖包。
