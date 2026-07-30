# Experiment Log

## EXP_001：研究级机器学习流程优化

### 实验状态

代码已准备，尚未运行。

### 实验日期

2026-07-29

### 实验目的

在不改写原始 Notebook 和既有结果的前提下，将数据处理、模型验证和策略回测整理为可审计的时间序列研究流程。

### 研究假设

- 真实交易日历和交易时段内处理可以避免非交易日及跨时段填充污染。
- 严格的 Train、Validation、Test 时间划分可以降低随机切分带来的信息泄露风险。
- 使用非重叠增量收益及按仓位变化计费，可以减少原回测的收益重复计算和成本低估。

以上为待验证假设，不代表已取得实验结论。

### 输入与数据范围

- `features.pkl`：来源于已有数据处理流程。
- `trading_calendar.csv`：待提供的真实交易日历。
- 合约、样本日期与最终数据版本：待实际运行后记录。
- 预测目标：同一交易时段内未来 3 秒 `last_price return`。

### 代码版本

- [[../05_Code/revised/README|Revised Notebooks]]
- `ML1_homework.ipynb`
- `Modeling.ipynb`
- `Modeling_Backtest.ipynb`

### 参数与方法

- 数据只在真实交易日、同一日内交易时段内处理，禁止跨交易日或跨时段 `ffill`。
- `D_k`、`effective_spread`、`avg_price` 使用严格滞后一条快照的版本。
- 数据按日期顺序划分为 Train、Validation、Test，Test 默认锁定。
- Ridge、Decision Tree、LightGBM 保留为主要实际模型；SVM 默认关闭。
- LightGBM 使用固定随机种子、时间靠后的 Validation、Early Stopping 和 Feature Importance。
- 回测使用下一快照执行、非重叠 500ms 增量 PnL，并按 `abs(position变化)` 计算成本。

### 实验结果

尚未运行，不记录指标或收益结果。

### 实验结论

待三个 revised Notebook 按顺序运行后填写。

### 后续行动

1. 准备并核验真实交易日历。
2. 运行 revised 数据处理 Notebook，检查质量报告和时间划分。
3. 运行 revised 模型 Notebook，只使用 Validation 完成研究决策。
4. 运行 Validation 回测并冻结信号阈值。
5. 研究设计冻结后，单次运行最终 Test 评价。

## 历史实验状态

原始 Notebook 中可以确认以下实验线索，但缺少统一的 Experiment ID、数据版本、运行时间和完整结论：

- Ridge 回归训练与预测评价。
- RBF-SVR 训练与预测评价。
- 单棵 Decision Tree 训练与预测评价。
- LightGBM 单次验证集训练、特征重要性筛选和五折预测。
- Ridge、SVR、Decision Tree、LightGBM 的阈值策略回测。
- 多组滑点和手续费敏感性比较。
- MLP、SA-GRU 和 Transformer 的探索性训练。

保存输出仍在迁移后的 Notebook 中：

- 模型预测结果：[[../05_Code/02_model_training/README|Modeling.ipynb]]
- 策略回测结果：[[../05_Code/03_backtest/README|Modeling_Backtest.ipynb]]

本次不整理具体指标，不根据这些输出补写历史调参过程或重新判断最优模型。Linear Regression、Lasso 和 Random Forest 未形成独立实验，不在历史实验线索中补建记录。

---

## 实验记录模板

### Experiment ID

待填写，例如 `EXP_001`。

### 实验日期

待填写。

### 实验目的

待填写。

### 研究假设

待填写。

### 数据范围

- 合约：
- 日期：
- 数据版本：
- 目标定义：

### 特征版本

待填写。

### 模型与参数

待填写。

### 回测设置

- 信号阈值：
- 滑点：
- 手续费：
- 执行延迟：
- 年化参数：

### 结果指标

- MSE：
- MAE：
- $R^2$：
- 累计收益：
- Sharpe：
- 最大回撤：

### 实验结果

待填写，不从缺失记录中推断。

### 实验结论

待填写。

### 已知问题

待填写。

### 后续行动

待填写。
