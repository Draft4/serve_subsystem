# 包清单与协作

| 包及文档 | 所属层级 | 工作空间 | 负责人 | 职责 | 状态 |
| --- | --- | --- | --- | --- | --- |
| [`tennis_serve_launcher_adapter`](../src/tennis_serve_launcher_adapter/wiki/README.md) | `04_actuation_control` | `launcher_actuation_ws` | 李弈坤、肖志豪（层级负责人；包维护人待确认） | 发球机构 ROS 指令到现有底层硬件话题的适配。 | 已实现；现场联调未验证 |

层级为 `04_actuation_control`；边界：把已获许可的发球和拨球目标转换为现有硬件 ROS 话题并汇总反馈；CAN 由既有底层负责。
源码与构建定义位于各包 `src/<包名>/`。共用接口只在
`00_shared/interfaces_ws/src/tennis_serve_interfaces/` 定义。发球定位来自
`/localization/robot_state`，朝向规划只计算当前位置所需 yaw，
发球参数规划输出轮速和俯仰目标；执行监督确认许可后才发布命令，
Adapter 负责对接现有硬件 ROS 话题。任务由 mission 编排，operator 只转换上位机请求。

输入输出细节以每个包的 [interfaces.md](../src/tennis_serve_launcher_adapter/wiki/interfaces.md)
和 `msg/srv/action` 源文件为准。跨组底盘朝向命令的订阅实现、真实俯仰反馈字段
仍需与执行控制组现场确认。
