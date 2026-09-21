# 实现、参数和验证

Action 执行中检查定位、朝向、速度、轮速、俯仰、位置偏移、急停与反馈；持续刷新 setpoint；每球只发布一次唯一 FeedCommand。

## 参数与假设

默认运行参数以 `config/*.yaml`、launch 文件和源码中 `declare_parameter`
为准。场地坐标统一为 `court_origin_v2`：本方底线左角为原点，X 向右，Y 朝球网；
yaw 为 0 时朝 +Y，逆时针为正。模型内部旧 Y 坐标只在模型边界转换一次。

## 限制与失败行为

拨球前门禁须持续稳定默认 0.2 s；位置偏移超过 0.5 m 持续 0.5 s 后中止；feedback 模式等待拨球结果默认 8.5 s。

## 验证

`test_contract_files.py` 静态检查部分契约；底盘订阅者、实机急停和拨球反馈需现场验证。
