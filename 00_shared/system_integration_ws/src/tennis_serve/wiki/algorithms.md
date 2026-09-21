# 实现、参数和验证

`tennis_serve.launch.py` 启动 aim、launcher planner、supervisor、mission、operator 五个节点；Adapter 由单独服务启动。

## 参数与假设

默认运行参数以 `config/*.yaml`、launch 文件和源码中 `declare_parameter`
为准。场地坐标统一为 `court_origin_v2`：本方底线左角为原点，X 向右，Y 朝球网；
yaw 为 0 时朝 +Y，逆时针为正。模型内部旧 Y 坐标只在模型边界转换一次。

## 限制与失败行为

依赖外部定位、`tennisbot_interfaces` 和 `tennisbot_launcher`；不启动硬件 Adapter，避免重复命令发布者。

## 验证

launch 文件可静态解析；RK3588 上的完整 ROS 图和 systemd 启动未验证。
