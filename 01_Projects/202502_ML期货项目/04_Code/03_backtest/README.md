# 策略回测 Notebook

## 文件

`Modeling_Backtest.ipynb`

原文件名为 `Modeling 1.ipynb`，迁移时仅重命名以明确职责。

## 作用

- 定义单一成本情景和多成本情景的回测函数。
- 将模型预测值按正负阈值转换为多空信号。
- 将信号延迟一个快照形成仓位。
- 扣除滑点和手续费。
- 计算累计收益、Sharpe 和最大回撤。
- 比较 Ridge、SVR、Decision Tree 与 LightGBM 的回测输出。
- 保留神经网络模型的探索性代码。

## 输入

- `features.pkl`
- `Train_data.pkl`
- `Test_data.pkl`
- 各模型预测值。

## 输出

- 包含信号、仓位、成本、净收益和资金曲线的 DataFrame。
- 回测指标字典。
- 不同成本情景的资金曲线。
- 多模型结果汇总 DataFrame。

这些输出保存在 Notebook 会话或嵌入输出中，没有迁移为新的结果文件。

具体回测指标暂不整理，结果位置保留在本 Notebook 的模型回测与汇总输出单元。

## 对应研究文档

- [[../../01_Research/技术路线|技术路线]]
- [[../../03_Model/模型评价|模型评价]]
- [[../../05_Experiment/experiment_log|Experiment Log]]
- [[../../06_Report/项目总结报告|项目总结报告]]

## 已知限制

- `bars_per_day=10000` 的年化假设需要核验。
- 交易成本按持仓变化时扣除固定比例，尚未建模盘口容量与真实撮合。
- 原始材料已指出潜在数据泄漏，现有回测结果不能直接视为稳健证据。
