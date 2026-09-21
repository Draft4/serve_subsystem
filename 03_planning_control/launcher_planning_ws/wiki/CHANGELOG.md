# 工作空间变更记录

## 未发布 — 简化模型加载

- 涉及包：`tennis_serve_launcher_planning`。
- 移除模型快照与 manifest 的运行时 SHA-256、版本一致性校验；模型快照的 SHA-256 仅作为状态追溯信息返回。
- 验证：本地 `test_model_relaxation.py` 通过；RK3588 在快照与 manifest 摘要不一致时仍可加载已修改的模型快照。
- Git commit/tag：待本次提交；未创建发布标签，`VERSION` 保持 `0.7.0`。

## 0.7.0 — 2026-09-21

- 涉及包：`tennis_serve_launcher_planning`。
- 当前代码从原单工作区按职责拆出；本次补齐两级 wiki、VERSION 和 Git 忽略规则。
- 验证：模型和核心逻辑已有本地测试；本次文档补齐后的完整板端运行**未验证**。
- 已知问题：负责人提交身份与统一 GitHub remote 待项目确认；板端定位、硬件和底盘接口需集成验证。
- Git commit/tag：协作仓库 `main` 的初始化提交；本次沿用包原有版本，未创建发布标签。远端备份状态以 `git status` 和远端分支核验。
