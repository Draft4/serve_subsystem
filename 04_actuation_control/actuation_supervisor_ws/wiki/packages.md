# 包清单与协作

| 包及文档 | 所属层级 | 工作空间 | 负责人 | 职责 | 状态 |
| --- | --- | --- | --- | --- | --- |
| [`tennis_serve_supervisor`](../src/tennis_serve_supervisor/wiki/README.md) | `04_actuation_control` | `actuation_supervisor_ws` | 李弈坤、肖志豪（层级负责人；包维护人待确认） | 单球执行动作、安全门禁与拨球许可。 | 已实现；现场联调未验证 |

层级为 `04_actuation_control`；边界：校验定位、朝向、机构反馈与急停，控制命令有效期和拨球时机。
源码与构建定义位于各包 `src/<包名>/`。共用接口只在
`00_shared/interfaces_ws/src/tennis_serve_interfaces/` 定义。发球定位来自
`/localization/robot_state`，朝向规划只计算当前位置所需 yaw，
发球参数规划输出轮速和俯仰目标；执行监督确认许可后才发布命令，
Adapter 负责对接现有硬件 ROS 话题。任务由 mission 编排，operator 只转换上位机请求。

输入输出细节以每个包的 [interfaces.md](../src/tennis_serve_supervisor/wiki/interfaces.md)
和 `msg/srv/action` 源文件为准。跨组底盘朝向命令的订阅实现、真实俯仰反馈字段
仍需与执行控制组现场确认。
