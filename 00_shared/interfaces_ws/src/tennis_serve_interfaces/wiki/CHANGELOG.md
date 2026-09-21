# tennis_serve_interfaces 变更记录

## 0.7.0 — 2026-09-21

- 功能/接口：跨层 msg、srv、action 合同。当前代码按层级归档，本次补齐包 wiki。
- 算法和配置：rosidl 生成接口；CourtTarget 和 PlannedShot 约定场地坐标及单球参数。修改字段须同步所有消费者。
- 测试结果：`ros2 interface show tennis_serve_interfaces/msg/PlannedShot`、`ros2 interface show tennis_serve_interfaces/action/ExecuteShot`；运行端到端图未验证。
- 已知限制：接口定义本身不提供消息时效或硬件安全保证；消费者按 `valid_until`、状态时间戳和任务 ID 执行检查。
- Git commit/tag：本地初始化提交后记录；沿用现有包版本，未创建发布标签。
