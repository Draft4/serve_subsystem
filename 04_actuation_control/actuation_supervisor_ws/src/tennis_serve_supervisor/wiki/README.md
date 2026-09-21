# tennis_serve_supervisor

版本：`0.7.0`；层级负责人：李弈坤、肖志豪（依据开发规范）；本包维护人待确认；所属工作空间：`actuation_supervisor_ws`。

单球执行动作、安全门禁与拨球许可。

## 依赖、配置和使用

依赖以 [`package.xml`](../package.xml) 为准。配置：supervisor.yaml。
先按工作空间 [README](../../../README.md) 构建并 source 环境。
生产环境由 `tennis_serve.launch.py` 组合启动；Adapter 使用独立
`launcher_adapter.launch.py`/systemd 服务。接口包和 common 包只作为依赖使用。

## 文档

- [实现与限制](algorithms.md)
- [模块和函数](functions.md)
- [输入输出接口](interfaces.md)
- [包版本记录](CHANGELOG.md)

完整 RK3588 联调与实球测试**未验证**。
