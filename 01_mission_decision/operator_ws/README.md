# 上位机 API 桥接

层级：`01_mission_decision`。版本：`0.7.0`。负责人：**待确认**（提交前按实际负责人填写）。

将 HTTP 请求和状态转换为 ROS 接口；不直接下发硬件命令。

包与文档：[工作空间 wiki](wiki/README.md) · [包清单](wiki/packages.md) · [版本记录](wiki/CHANGELOG.md)。

构建前安装 ROS 2 Jazzy，并按依赖顺序 source 上游工作空间。板端统一入口为
`/home/pi/Tennis_robot/00_shared/system_integration_ws/scripts/build_all.sh`；
运行环境由同目录下 `setup_env.sh` 提供。各工作空间迁入板端后保持层级目录结构，
在板端重新构建，不沿用本机 `build/`、`install/`、`log/`。
