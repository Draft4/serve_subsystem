# 实现、参数和验证

Job Manager 创建并管理训练步骤；每球请求 PlanShot，调用 ExecuteShot，运行期间续租飞轮保持；心跳丢失时暂停。

## 参数与假设

默认运行参数以 `config/*.yaml`、launch 文件和源码中 `declare_parameter`
为准。场地坐标统一为 `court_origin_v2`：本方底线左角为原点，X 向右，Y 朝球网；
yaw 为 0 时朝 +Y，逆时针为正。模型内部旧 Y 坐标只在模型边界转换一次。

## 限制与失败行为

`heartbeat_timeout_s` 默认 10 s；仅拨球前失败可按 `max_pre_feed_retries` 重试。

## 验证

任务编排需与真实定位和执行层联调；完整工作流未验证。
