# 实现、参数和验证

直接使用请求中的定位快照与场地目标，计算目标向量的 yaw；不规划发球路径。

## 参数与假设

默认运行参数以 `config/*.yaml`、launch 文件和源码中 `declare_parameter`
为准。场地坐标统一为 `court_origin_v2`：本方底线左角为原点，X 向右，Y 朝球网；
yaw 为 0 时朝 +Y，逆时针为正。模型内部旧 Y 坐标只在模型边界转换一次。

## 限制与失败行为

请求不含定位时间戳；新鲜度由 launcher planner 检查。异常目标返回 `PLAN_REJECTED`。

## 验证

`test/test_aim.py` 验证位置到朝向的纯函数；现场底盘到位未验证。
