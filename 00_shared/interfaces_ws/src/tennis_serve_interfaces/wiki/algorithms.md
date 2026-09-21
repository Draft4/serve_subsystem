# 实现、参数和验证

rosidl 生成接口；CourtTarget 和 PlannedShot 约定场地坐标及单球参数。修改字段须同步所有消费者。

## 参数与假设

默认运行参数以 `config/*.yaml`、launch 文件和源码中 `declare_parameter`
为准。场地坐标统一为 `court_origin_v2`：本方底线左角为原点，X 向右，Y 朝球网；
yaw 为 0 时朝 +Y，逆时针为正。模型内部旧 Y 坐标只在模型边界转换一次。

## 限制与失败行为

接口定义本身不提供消息时效或硬件安全保证；消费者按 `valid_until`、状态时间戳和任务 ID 执行检查。

## 验证

`ros2 interface show tennis_serve_interfaces/msg/PlannedShot`、`ros2 interface show tennis_serve_interfaces/action/ExecuteShot`；运行端到端图未验证。
