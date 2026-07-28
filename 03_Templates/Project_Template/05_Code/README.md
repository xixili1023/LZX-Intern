# Code

## 文件夹用途

承载项目专属代码开发，为数据处理、因子构建、模型、回测和实验复现提供实现。

## 应该存放什么

- `data/`：项目数据获取、清洗和转换代码
- `factor/`：因子计算与信号生成代码
- `model/`：模型训练、推断和评价代码
- `backtest/`：组合构建、交易模拟和绩效计算代码
- `utils/`：项目内部通用工具
- 依赖、配置、运行入口和测试说明

## 不应该存放什么

- 原始数据、处理后数据或大型回测结果
- 虚拟环境、缓存、临时 Notebook 输出和密钥
- 与项目无关的公共工具；成熟后应沉淀到 [[02_Assets/Code/README|Public Code Assets]]
- 只能手工运行且没有说明的不可复现脚本

## 与其他模块的关系

- 实现 [[02_Data/README|Data]]、[[03_Factors/README|Factors]] 和 [[04_Backtest/README|Backtest]] 中定义的方法。
- 每次关键运行由 [[06_Experiment/experiment_log|Experiment Log]] 记录实验条件，并关联对应 Git commit。
- 支撑 [[07_Report/README|Report]] 中的结果复现。
- 方法设计仍应记录在 [[01_Research/README|Research]]，不以代码替代研究说明。
