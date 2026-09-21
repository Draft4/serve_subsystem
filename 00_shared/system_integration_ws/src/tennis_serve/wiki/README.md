# tennis_serve

版本：`0.7.0`；负责人：**待确认**；所属工作空间：`system_integration_ws`。

跨层发球节点的 launch 和 systemd 集成包。

## 依赖、配置和使用

依赖以 [`package.xml`](../package.xml) 为准。配置：无独立 YAML，见源码默认值或 launch。
先按工作空间 [README](../../../README.md) 构建并 source 环境。
生产环境由 `tennis_serve.launch.py` 组合启动；Adapter 使用独立
`launcher_adapter.launch.py`/systemd 服务。接口包和 common 包只作为依赖使用。

## 文档

- [实现与限制](algorithms.md)
- [模块和函数](functions.md)
- [输入输出接口](interfaces.md)
- [包版本记录](CHANGELOG.md)

完整 RK3588 联调与实球测试**未验证**。
