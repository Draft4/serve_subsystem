# 实现、参数和验证

接收实时定位，调用 PlanAim，读取随包安装的模型快照，输出 PlannedShot；规划时不下发硬件命令。

## 参数与假设

默认运行参数以 `config/*.yaml`、launch 文件和源码中 `declare_parameter`
为准。场地坐标统一为 `court_origin_v2`：本方底线左角为原点，X 向右，Y 朝球网；
yaw 为 0 时朝 +Y，逆时针为正。模型内部旧 Y 坐标只在模型边界转换一次。

## 限制与失败行为

定位失效返回 `LOCALIZATION_NOT_READY`；目标或模型拒绝返回 `PLAN_REJECTED`。模型边界容差默认 1 m，外推结果以 confidence 标识。

## 验证

`test/test_model_relaxation.py` 验证边界和外推；模型快照 SHA-256 已与 manifest 核对，实球落点未验证。

## 模型数据清单

| 文件 | 来源与用途 | 版本 | SHA-256 |
| --- | --- | --- | --- |
| `data/fire_ball/model_snapshot.json` | 发球训练表导出的参数模型；用于轮速和俯仰规划 | `tennis-launcher-strategy-v1.1.0` | `ac8348450aa264422c7697c8473bde567dadaf15f5407e7fd1e7cb8ed170cea4` |
| 原始训练表（快照元数据记为 `发球数据_0907_0912合并_含轨迹参数.xlsx`；manifest 列为 `training_data.xlsx`） | 模型来源文件，当前工作空间未包含 | 待补充 | manifest 记录 `6128302d2d0417be0fc9dd89a99d06ef1cf8eabdba5012eabeb615aa53979746`，但本地文件未核验 |

快照哈希已在本地重新计算并与 `manifest.json` 对照。manifest 中还列有
`training_data.xlsx`、`requirements.txt`、`example_usage.py`、`README.md`，
这些文件目前不在已拆分的模型数据目录中；取得原始资料后应补齐并逐项核对。
