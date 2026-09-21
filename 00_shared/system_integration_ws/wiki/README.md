# 发球系统集成

所属层级：`00_shared`；工作空间：`system_integration_ws`；版本：`0.7.0`。
负责人：**待确认**。组合现有节点、部署环境与跨层验证；不承载核心算法。

## 协作仓库与部署

板端部署前，`serve_planning_ws` 只是发球组协同修改和优化代码的临时目录；
其中的 `serve_subsystem` 是[协作 Git 仓库](https://github.com/Draft4/serve_subsystem)。
两级目录都不作为板端运行路径，也不需要一起复制到 RK3588。
开发阶段跨工作空间的接口改动在同一仓库提交；部署时只迁移各个工作空间，
按下表所属层级放在 `/home/pi/Tennis_robot/<层级>/<工作空间>_ws`，并在板端重建。
运行时代码、launch、服务模板和配置不依赖临时目录名称。

| 层级 | 工作空间 | 职责 |
| --- | --- | --- |
| `00_shared` | [interfaces_ws](../../../00_shared/interfaces_ws/README.md) | 跨层接口与公共坐标计算 |
| `00_shared` | [system_integration_ws](../README.md) | 组合启动、构建脚本与部署模板 |
| `01_mission_decision` | [mission_ws](../../../01_mission_decision/mission_ws/README.md) | 任务状态机、逐球调度和心跳 |
| `01_mission_decision` | [operator_ws](../../../01_mission_decision/operator_ws/README.md) | Windows 上位机的 HTTP/ROS 接口 |
| `03_planning_control` | [serve_planning_ws](../../../03_planning_control/serve_planning_ws/README.md) | 从当前位置计算发球朝向，无发球路径规划 |
| `03_planning_control` | [launcher_planning_ws](../../../03_planning_control/launcher_planning_ws/README.md) | 轮速、俯仰与模型参数规划 |
| `04_actuation_control` | [actuation_supervisor_ws](../../../04_actuation_control/actuation_supervisor_ws/README.md) | 执行许可、安全门禁与拨球时机 |
| `04_actuation_control` | [launcher_actuation_ws](../../../04_actuation_control/launcher_actuation_ws/README.md) | 将命令适配到现有硬件 ROS 话题 |

任务层决定何时发球；规划层只输出朝向和发球参数目标；执行监督层检查许可并发布
底盘朝向、发球机参数和拨球命令；Adapter 对接既有硬件 ROS 接口。
本组代码不接管 CAN/F407 驱动。移入板端时不复制本地 `build/`、`install/`、`log/`
或本机凭据。若后续将协作仓库拆成独立仓库，应保留版本记录并核对跨工作空间依赖。

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

## 当前板端验证状态

2026-09-21 在 RK3588 上将本组 8 个工作空间的旧 `build/`、`install/`、`log/`
移到板端备份目录后，按 `scripts/build_all.sh` 完成清洁构建，共构建 9 个包；
使用 `scripts/setup_env.sh` 可导入关键 Python 模块并加载发球模型。相关 33 项
单元测试通过，集成 launch 的参数解析通过。完整 ROS 图与实球发射尚未验证。

板端现有 `tennisbot_launcher/msg/LauncherPitchState` 无实测俯仰角字段。发球 Adapter
已改为只下发俯仰命令，以命令角度作为估算值；发球许可不校验实际俯仰反馈。现有
`tennis-serve-launcher-adapter.service` 虽已启用，
其已安装的 unit 仍指向旧 `/home/pi/tennis_serve/ros2_ws`，启用新版本前需更新
systemd unit。板端本次未启动发球相关服务。
