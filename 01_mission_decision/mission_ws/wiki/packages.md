# 包清单与协作

| 包及文档 | 所属层级 | 工作空间 | 负责人 | 职责 | 状态 |
| --- | --- | --- | --- | --- | --- |
| [`tennis_serve_mission`](../src/tennis_serve_mission/wiki/README.md) | `01_mission_decision` | `mission_ws` | 待确认 | 训练任务状态机、心跳和逐球编排。 | 已实现；现场联调未验证 |

层级为 `01_mission_decision`；边界：管理训练任务、心跳、暂停和逐球调度；执行动作由执行监督层完成。
源码与构建定义位于各包 `src/<包名>/`。共用接口只在
`00_shared/interfaces_ws/src/tennis_serve_interfaces/` 定义。发球定位来自
`/localization/robot_state`，朝向规划只计算当前位置所需 yaw，
发球参数规划输出轮速和俯仰目标；执行监督确认许可后才发布命令，
Adapter 负责对接现有硬件 ROS 话题。任务由 mission 编排，operator 只转换上位机请求。

输入输出细节以每个包的 [interfaces.md](../src/tennis_serve_mission/wiki/interfaces.md)
和 `msg/srv/action` 源文件为准。跨组底盘朝向命令的订阅实现、真实俯仰反馈字段
仍需与执行控制组现场确认。
