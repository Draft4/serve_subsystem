# tennis_serve 变更记录

## 0.7.0 — 2026-09-21

- 功能/接口：跨层发球节点的 launch 和 systemd 集成包。当前代码按层级归档，本次补齐包 wiki。
- 算法和配置：`tennis_serve.launch.py` 启动 aim、launcher planner、supervisor、mission、operator 五个节点；Adapter 由单独服务启动。
- 测试结果：launch 文件可静态解析；RK3588 上的完整 ROS 图和 systemd 启动未验证。
- 已知限制：依赖外部定位、`tennisbot_interfaces` 和 `tennisbot_launcher`；不启动硬件 Adapter，避免重复命令发布者。
- Git commit/tag：本地初始化提交后记录；沿用现有包版本，未创建发布标签。
