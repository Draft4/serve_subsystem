# tennis_serve_mission 变更记录

## 0.7.0 — 2026-09-21

- 功能/接口：训练任务状态机、心跳和逐球编排。当前代码按层级归档，本次补齐包 wiki。
- 算法和配置：Job Manager 创建并管理训练步骤；每球请求 PlanShot，调用 ExecuteShot，运行期间续租飞轮保持；心跳丢失时暂停。
- 测试结果：任务编排需与真实定位和执行层联调；完整工作流未验证。
- 已知限制：`heartbeat_timeout_s` 默认 10 s；仅拨球前失败可按 `max_pre_feed_retries` 重试。
- Git commit/tag：本地初始化提交后记录；沿用现有包版本，未创建发布标签。
