# Experiment

## 文件夹用途

独立保存量化研究实验过程，包括参数测试、因子组合实验、回测方案比较和模型迭代。

## 应该存放什么

- `experiment_log.md`：实验目的、假设、参数、数据范围、方法、结果、结论和后续行动
- 每项实验的唯一 Experiment ID 和实验日期
- 成功、失败及不利实验的客观记录
- 指向研究文档、回测结果和对应 Git commit 的链接

## 不应该存放什么

- 仅用于描述代码变化的版本日志
- `CHANGELOG.md`
- 大型运行产物、缓存或可以重建的临时文件
- 缺少实验条件与结论的孤立结果

## 与其他模块的关系

- 实验目的和研究假设来自 [[01_Research/README|Research]]。
- 实验使用 [[02_Data/README|Data]] 的明确数据范围和版本。
- 因子实验关联 [[03_Factors/README|Factors]]。
- 回测方案和结果关联 [[04_Backtest/README|Backtest]]。
- 实现版本通过 [[05_Code/README|Code]] 对应的 Git commit 固定。
- 实验结论为 [[07_Report/README|Report]] 提供证据。

