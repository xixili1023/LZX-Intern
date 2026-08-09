# Revised Notebooks

本目录保存研究级优化版本。优化目标是提高时间序列研究的可审计性、可复现性和回测可信度，不承诺提高预测指标或策略收益。

## 文件与运行顺序

1. `ML1_homework.ipynb`
   - 按真实交易日历与日内时段处理数据。
   - 禁止跨交易日、跨午休时段前值填充。
   - 生成按时间划分的 Train、Validation、Test 数据。
2. `Modeling.ipynb`
   - 使用 Train 训练、Validation 选定研究设置。
   - Test 默认锁定，仅在参数、特征和阈值冻结后用于最终评价。
   - 输出 Validation 预测、评价指标与 LightGBM Feature Importance。
3. `Modeling_Backtest.ipynb`
   - 将预测转为下一快照执行的仓位。
   - 使用非重叠 500ms 增量收益记账。
   - 按绝对仓位变化扣除价差、手续费和额外滑点。

## 输入

- `/Users/lizhexi/Desktop/InternData/ML期货项目Data/processed/features.pkl`：由已有上游数据处理流程生成。
- `/Users/lizhexi/Desktop/InternData/ML期货项目Data/processed/trading_calendar.csv`：真实交易日历，至少包含 `trade_date`。
- 可通过环境变量 `ML_FUTURES_DATA_ROOT` 覆盖项目数据根目录。
- Python 环境及 Notebook 中导入的依赖。

## 输出

- 数据集与质量报告：`/Users/lizhexi/Desktop/InternData/ML期货项目Data/processed/revised/`
- 模型与回测中间结果：`04_Code/revised/artifacts/`

这些输出只有在实际运行 Notebook 后才会生成。当前目录不包含补造的实验结果。

## 研究边界

- 当前数据流程只纳入日盘；夜盘需要先明确交易日映射。
- `D_k`、`effective_spread` 和 `avg_price` 只使用严格滞后一条快照的版本。
- Linear Regression 与 Random Forest 只保留模型体系说明，不补建不存在的历史实验。
- SVM 保留原研究逻辑，但默认关闭以避免在高频大样本上意外触发高成本训练。
- 运行结果应同步记录到 [[../../05_Experiment/experiment_log|Experiment Log]]。
