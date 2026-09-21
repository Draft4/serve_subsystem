# 包清单与协作

| 包及文档 | 所属层级 | 工作空间 | 负责人 | 职责 | 状态 |
| --- | --- | --- | --- | --- | --- |
| [`tennis_serve_launcher_planning`](../src/tennis_serve_launcher_planning/wiki/README.md) | `03_planning_control` | `launcher_planning_ws` | 路遥（开发规范） | 落点到轮速、俯仰和目标朝向的单球规划组合。 | 已实现；现场联调未验证 |

层级为 `03_planning_control`；边界：用参数模型计算上下轮 RPM 与俯仰目标；不控制电机或拨球。
源码与构建定义位于各包 `src/<包名>/`。共用接口只在
`00_shared/interfaces_ws/src/tennis_serve_interfaces/` 定义。发球定位来自
`/localization/robot_state`，朝向规划只计算当前位置所需 yaw，
发球参数规划输出轮速和俯仰目标；执行监督确认许可后才发布命令，
Adapter 负责对接现有硬件 ROS 话题。任务由 mission 编排，operator 只转换上位机请求。

输入输出细节以每个包的 [interfaces.md](../src/tennis_serve_launcher_planning/wiki/interfaces.md)
和 `msg/srv/action` 源文件为准。跨组底盘朝向命令的订阅实现、真实俯仰反馈字段
仍需与执行控制组现场确认。
