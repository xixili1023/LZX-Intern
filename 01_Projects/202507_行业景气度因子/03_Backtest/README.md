# Backtest

## 文件夹用途

管理回测设计、参数、交易约束、绩效评价和结果产物索引，保证回测过程可审查。

## 应该存放什么

- `回测框架.md`：时间推进、信号执行、组合构建和评价逻辑
- `参数设置.md`：样本、调仓、成本、风险和敏感性参数
- `results/`：本地生成的回测结果、图表或结果文件
- 偏差检查、稳健性检验与结果解释

## 不应该存放什么

- 回测实现源代码
- 无参数、无数据版本或无代码版本的孤立结果
- 人工筛选后无法复现的图表
- 应由 Git 跟踪的关键研究结论仅以二进制文件保存

## 与其他模块的关系

- 回测设计验证 [[01_Research/README|Research]] 与 [[02_Factors/README|Factors]] 的假设。
- 使用 [项目外部数据说明](/Users/lizhexi/Desktop/InternData/行业景气度项目Data/README.md) 定义的数据版本。
- 实现代码位于 [[04_Code/README|Code]] 的 `backtest/`。
- 每次正式运行登记到 [[05_Experiment/experiment_log|Experiment Log]]，并关联 [[04_Code/README|Code]] 的 Git commit。
- 关键结果与限制进入 [[06_Report/README|Report]]。

## 已迁移内容

- [[回测框架|候选池、收益口径、调仓、成本、股票池与评价指标]]
- [[参数设置|原文参数和待确认参数]]

`results/` 当前保持为空，本次没有生成或迁移回测结果文件。
