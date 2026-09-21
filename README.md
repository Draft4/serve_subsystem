# 发球子系统临时协作仓库

`serve_subsystem` 用于发球组在部署到 RK3588 之前协同修改、测试和优化代码。
它是 Git 协作仓库的根目录，不是 ROS 2 工作空间，也不是板端部署目录。
完成开发后，**只将下面的各个工作空间分别迁入板端对应层级**；不把整个
`serve_subsystem` 目录复制到板端。源码、launch、服务模板和配置不依赖这个
临时目录的名称。

## 工作空间与职责

| 层级 | 工作空间 | 主要职责 |
| --- | --- | --- |
| `00_shared` | [interfaces_ws](00_shared/interfaces_ws/README.md) | 公共 ROS 接口和场地坐标计算 |
| `00_shared` | [system_integration_ws](00_shared/system_integration_ws/README.md) | 构建顺序、环境脚本、组合启动和部署模板 |
| `01_mission_decision` | [mission_ws](01_mission_decision/mission_ws/README.md) | 训练任务、状态机、逐球调度和心跳 |
| `01_mission_decision` | [operator_ws](01_mission_decision/operator_ws/README.md) | Windows 上位机 HTTP/ROS 通信 |
| `03_planning_control` | [serve_planning_ws](03_planning_control/serve_planning_ws/README.md) | 根据当前机器人位置和目标计算发球朝向 |
| `03_planning_control` | [launcher_planning_ws](03_planning_control/launcher_planning_ws/README.md) | 规划上下轮转速、俯仰和模型参数 |
| `04_actuation_control` | [actuation_supervisor_ws](04_actuation_control/actuation_supervisor_ws/README.md) | 执行许可、安全门禁、单球动作和拨球时机 |
| `04_actuation_control` | [launcher_actuation_ws](04_actuation_control/launcher_actuation_ws/README.md) | 发球/拨球目标到现有硬件 ROS 话题的适配与反馈 |

发球在机器人当前位置进行，只需调整朝向，**不生成发球路径或底盘轨迹**。
任务层决定何时发球；规划层给出朝向、转速和俯仰目标；执行监督层通过安全门禁后
发布底盘朝向、发球机参数和拨球命令；Adapter 对接已有硬件 ROS 接口。
本仓库不接管 CAN、F407 驱动，也不直接控制电机。

## 协作与板端部署

协作阶段统一使用 [Draft4/serve_subsystem](https://github.com/Draft4/serve_subsystem)
仓库提交跨工作空间改动。每个工作空间保留自己的 `VERSION`、`README.md` 和两级
`wiki/`；接口、算法、函数与变更记录从上表进入。提交时同步修改相关代码与文档，
检查暂存内容，不提交凭据或本机构建产物。

板端按规范层级放置工作空间，例如：

```text
/home/pi/Tennis_robot/
├── 00_shared/{interfaces_ws,system_integration_ws}/
├── 01_mission_decision/{mission_ws,operator_ws}/
├── 03_planning_control/{serve_planning_ws,launcher_planning_ws}/
└── 04_actuation_control/{actuation_supervisor_ws,launcher_actuation_ws}/
```

迁移各工作空间的源码、默认配置、必要模型和 wiki，在板端重新构建；不迁移
`build/`、`install/`、`log/`、缓存或本机私有配置。现有定位与设备工作空间是
外部依赖，提供 `tennisbot_interfaces` 和 `tennisbot_launcher`。部署路径、
构建顺序和运行环境见 [系统集成工作空间说明](00_shared/system_integration_ws/README.md)。
生产启动由 `tennis_serve` 集成 launch 与独立的 Adapter 服务组成；不要同时重复启动
Adapter。板端已完成 9 包清洁构建及 33 项单元测试；完整 ROS 图和实球效果仍需现场验证。
当前板端俯仰状态接口缺少实测角度，Adapter 会按默认安全门禁阻止发球；
已安装的发球 systemd unit 仍指向旧路径，启用新版本前需更新。

模型快照随 `launcher_planning_ws` 版本管理；
[模型说明](03_planning_control/launcher_planning_ws/src/tennis_serve_launcher_planning/wiki/algorithms.md)
记录其来源、SHA-256 及尚未取得的原始训练表。未来若把工作空间拆成独立仓库，
须保留各自版本记录并重新核对跨工作空间依赖。
