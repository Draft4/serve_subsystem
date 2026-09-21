# 模块与主要函数

`launch/tennis_serve.launch.py`：节点组合及参数文件；`deploy/tennis-serve.service`：板端服务；`test/manual_fake_io_node.py`：隔离联调工具。

输入输出与异常：提供 `ros2 launch tennis_serve tennis_serve.launch.py` 启动入口；不定义新的消息或服务。运行中的 ROS 接口详见各功能包。

| 入口 | 输入 → 输出 | 失败行为 |
| --- | --- | --- |
| `generate_launch_description()` | 各包 share 目录的配置文件 → 五节点 LaunchDescription | 缺包或缺配置时 launch 报错 |
| `scripts/build_all.sh` | 已安装的 ROS 和外部 underlay → 各工作空间 `install/` | 任一构建失败即退出 |
| `scripts/setup_env.sh` | 各工作空间 `install/local_setup.bash` → 当前 shell 环境 | 缺少 underlay 时后续节点无法启动 |
| `manual_fake_io_node.py` | 测试用命令话题 → 虚拟状态 | 仅隔离联调；不由生产 launch 启动 |
