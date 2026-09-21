# tennis_serve_operator 变更记录

## 0.7.0 — 2026-09-21

- 功能/接口：上位机 HTTP/JSON 与 ROS 任务接口转换。当前代码按层级归档，本次补齐包 wiki。
- 算法和配置：FastAPI 提供健康、状态、模型、预览、任务创建/查询/命令/心跳和急停复位；Bearer Token 从 `TENNIS_API_TOKEN` 读取。
- 测试结果：可用 `/api/v1/health` 和 `/api/v1/status` 冒烟；上位机联调未验证。
- 已知限制：只转换和显示状态；是否允许执行由任务及执行层判断。Token 不得写入版本库。
- Git commit/tag：本地初始化提交后记录；沿用现有包版本，未创建发布标签。
