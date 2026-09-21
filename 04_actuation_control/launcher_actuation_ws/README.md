# 发球机构 ROS 适配

层级：`04_actuation_control`。版本：`1.3.0`。层级负责人：李弈坤、肖志豪（依据开发规范）；本仓库维护人待确认。

把已获许可的发球和拨球目标转换为现有硬件 ROS 话题并汇总反馈；CAN 由既有底层负责。

包与文档：[工作空间 wiki](wiki/README.md) · [包清单](wiki/packages.md) · [版本记录](wiki/CHANGELOG.md)。

构建前安装 ROS 2 Jazzy，并按依赖顺序 source 上游工作空间。板端统一入口为
`/home/pi/Tennis_robot/00_shared/system_integration_ws/scripts/build_all.sh`；
运行环境由同目录下 `setup_env.sh` 提供。各工作空间迁入板端后保持层级目录结构，
在板端重新构建，不沿用本机 `build/`、`install/`、`log/`。
