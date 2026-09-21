# 实现、参数和验证

FastAPI 提供健康、状态、模型、预览、任务创建/查询/命令/心跳和急停复位；Bearer Token 从 `TENNIS_API_TOKEN` 读取。

## 参数与假设

默认运行参数以 `config/*.yaml`、launch 文件和源码中 `declare_parameter`
为准。场地坐标统一为 `court_origin_v2`：本方底线左角为原点，X 向右，Y 朝球网；
yaw 为 0 时朝 +Y，逆时针为正。模型内部旧 Y 坐标只在模型边界转换一次。

## 限制与失败行为

只转换和显示状态；是否允许执行由任务及执行层判断。Token 不得写入版本库。

## 验证

可用 `/api/v1/health` 和 `/api/v1/status` 冒烟；上位机联调未验证。
