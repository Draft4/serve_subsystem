# 单球执行监督

所属层级：`04_actuation_control`；工作空间：`actuation_supervisor_ws`；版本：`0.7.0`。
层级负责人：李弈坤、肖志豪（依据开发规范）；本仓库维护人待确认。校验定位、朝向、机构反馈与急停，控制命令有效期和拨球时机。

## 协作仓库与部署

开发阶段统一在一个协作 Git 仓库中维护本工作空间与其余发球工作空间，
同一次跨工作空间接口改动共同提交。板端部署时只迁移本工作空间目录，
仍按所属层级放置并重新构建；运行时不依赖协作仓库的上层目录。
若后续拆为独立仓库，应保留版本记录并核对跨工作空间依赖。

## 依赖与环境

ROS 2 Jazzy；公共接口工作空间 `00_shared/interfaces_ws`；外部定位工作空间提供
`tennisbot_interfaces`，现有设备工作空间提供 `tennisbot_launcher`。
只有本工作空间实际声明的依赖才需在对应节点运行时存在，详见各包 `package.xml`。
板端当前外部 underlay 为 `/home/pi/localization_ws` 和
`/home/pi/Tennis_robot/05_device_drivers/can_gateway_ws`；本组工作空间按层级放在
`/home/pi/Tennis_robot/` 下。无需启动的工作空间可独立构建；完整系统按
`00_shared/system_integration_ws/scripts/build_all.sh` 的顺序构建。

## 文档

- [包清单和协作关系](packages.md)
- [工作空间版本记录](CHANGELOG.md)
- [源码入口](../src/)

本次仅补齐文档和仓库结构；RK3588 的完整 ROS 图与实球测试**未验证**。
