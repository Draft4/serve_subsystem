# tennis_serve_launcher_planning 变更记录

## 未发布 — 简化模型加载

- 移除 `model_snapshot.json` 与 `manifest.json` 的运行时 SHA-256 和版本一致性校验；规划节点仅加载模型快照。
- SHA-256 继续通过模型信息接口返回，用于追溯当前已加载的模型文件。
- 验证：`test/test_model_relaxation.py` 通过。

## 0.7.0 — 2026-09-21

- 功能/接口：落点到轮速、俯仰和目标朝向的单球规划组合。当前代码按层级归档，本次补齐包 wiki。
- 算法和配置：接收实时定位，调用 PlanAim，读取随包安装的模型快照，输出 PlannedShot；规划时不下发硬件命令。
- 测试结果：`test/test_model_relaxation.py` 验证边界和外推；实球落点未验证。
- 已知限制：定位失效返回 `LOCALIZATION_NOT_READY`；目标或模型拒绝返回 `PLAN_REJECTED`。模型边界容差默认 1 m，外推结果以 confidence 标识。
- Git commit/tag：本地初始化提交后记录；沿用现有包版本，未创建发布标签。
