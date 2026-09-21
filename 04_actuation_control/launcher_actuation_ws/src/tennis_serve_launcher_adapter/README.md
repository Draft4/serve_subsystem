# tennis_serve_launcher_adapter

本包位于 `04_actuation_control/launcher_actuation_ws/src/`。
构建和启动入口位于 `00_shared/system_integration_ws/scripts/`。

该 ROS 2 Python 包负责发球指令与现有硬件话题之间的适配。

它只启动：

```text
serve_launcher_adapter_node
```

不会重复启动其他工作空间中的：

```text
serve_aim_node
serve_planner_node
serve_controller_node
serve_job_manager_node
serve_bridge_node
```

## 复制位置

将整个 `tennis_serve_launcher_adapter` 文件夹复制到：

```text
/home/pi/Tennis_robot/04_actuation_control/launcher_actuation_ws/src/
```

复制后目录应为：

```text
/home/pi/Tennis_robot/04_actuation_control/launcher_actuation_ws/src/tennis_serve_launcher_adapter/
├── package.xml
├── setup.py
├── setup.cfg
├── config/
├── launch/
├── resource/
├── tennis_serve_launcher_adapter/
└── test/
```

## 构建

```bash
bash /home/pi/Tennis_robot/00_shared/system_integration_ws/scripts/build_all.sh
source /home/pi/Tennis_robot/00_shared/system_integration_ws/scripts/setup_env.sh
```

## 手动调试启动

安装systemd服务前，可单独调试Adapter：

```bash
source /home/pi/Tennis_robot/00_shared/system_integration_ws/scripts/setup_env.sh

ros2 launch \
  tennis_serve_launcher_adapter \
  launcher_adapter.launch.py
```

## 验证

```bash
ros2 node list | grep serve_launcher_adapter_node

ros2 topic info /tennis/launcher/setpoint
ros2 topic info /tennis/launcher/feed_command
ros2 topic info /tennis/launcher/state
```

正常结果：

```text
/tennis/launcher/setpoint     Subscription count: 1
/tennis/launcher/feed_command Subscription count: 1
/tennis/launcher/state        Publisher count: 1
```

只读检查：

```bash
ros2 topic echo --once /tennis/launcher/state \
  --qos-reliability best_effort
```

## 配置为开机启动

确认手动启动和只读状态检查正常后执行：

```bash
sudo install -o root -g root -m 0644 \
  /home/pi/Tennis_robot/04_actuation_control/launcher_actuation_ws/src/tennis_serve_launcher_adapter/deploy/tennis-serve-launcher-adapter.service \
  /etc/systemd/system/tennis-serve-launcher-adapter.service

sudo systemctl daemon-reload
sudo systemctl enable --now tennis-serve-launcher-adapter.service
```

检查：

```bash
systemctl status tennis-serve-launcher-adapter.service --no-pager
journalctl -u tennis-serve-launcher-adapter.service -n 100 --no-pager
```

启用systemd服务后，主 `tennis_serve.launch.py` 不会启动Adapter。不要再从终端手动启动
`launcher_adapter.launch.py`，否则会产生两个同名节点和两个硬件命令发布者。

## 停止

在运行 launch 的终端按：

```text
Ctrl+C
```

适配节点退出后，`launcher_ros_control` 的命令超时机制会停止发球轮。

## 注意

- 不要同时运行旧的 `serve_launcher_adapter_node`。
- 外部 `LauncherSetpoint` 必须周期发布并更新 `valid_until`。
- 上轮方向为 `+1`，下轮方向为 `-1`。
- 对外机械转速限制为 `0～7857 rpm`。
- 一次 FEED 必须使用唯一 `command_id`。
- 默认 `allow_open_loop_pitch=false`。只有 `LauncherPitchState` 提供真实角度字段时
  `pitch_valid` 才会为 true；严禁在实球测试中把 commanded angle 冒充实际角度。
- 默认检查轮速反馈的正负方向。若底层只能返回无符号 RPM，必须在确认机械方向后才能将
  `enforce_feedback_direction` 改为 false。
- 启动时会检查 `tennisbot_launcher` 六种消息所需字段，接口不匹配会立即报出缺失字段，
  不再等到收到第一条命令后才异常。
- Adapter 的拨球结果超时为 8 秒；配套 Controller 的 `feed_confirmation_timeout_s` 应大于
  该值。当前推荐配置为 `feedback` 模式和 8.5 秒。
