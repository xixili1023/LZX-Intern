# 202502 ML 期货高频预测项目

## 项目定位

本项目由研究生机器学习课程作业迁移而来，研究对象为铜期货半秒级盘口快照，目标是利用高频特征预测未来短周期价格收益，并将预测结果转化为交易信号进行回测。

迁移工作的目标是整理研究逻辑、模型解释和代码入口，不重新训练模型、不修改已有实验结果，也不将课程项目包装成未经验证的研究成果。

## 核心研究问题

- 当前盘口和订单流信息能否解释未来 3 秒的价格变化？
- 不同类型的高频特征对短周期预测有什么作用？
- 线性模型、树模型、SVM 与 LightGBM 在本问题中分别承担什么比较角色？
- 加入信号阈值、滑点和手续费后，模型预测是否仍具有交易意义？

## 重要口径说明

根据现有 Notebook，正式预测目标为：

$$
return_t=\frac{last\_price_{t+6}}{last\_price_t}-1
$$

半秒频率下对应未来 3 秒的 `last_price return`。

`last_price` 本身位于数据表第 2 列，而模型使用 `iloc[:, 2:-3]` 选择特征，因此没有直接进入模型。但是以下实际特征依赖当前 `last_price`：

- `D_k`：根据 `last_price` 相对买一、卖一中间价的位置判断成交方向；
- `effective_spread`：使用 `last_price` 与 `mid_price_t` 的差构造；
- `avg_price`：当 `vol == 0` 时由 `last_price` 赋值，之后进入特征处理范围。

这些变量存在潜在时间泄漏风险：订单簿中的 `last_price` 依赖当前时刻成交结果；相对于仅使用盘口形成信号的决策时点，它属于包含未来成交信息的价格变量，可能导致模型提前获得未来信息。实际影响仍需根据 FastBox 快照的撮合与时间戳定义确认。

现有结果只保留在 Notebook 中，不在项目文档中整理具体指标。

## 项目入口

- 项目概况：[[00_Project_Profile/项目简介|项目简介]]
- 研究框架：[[01_Research/研究框架|研究框架]]
- 数据说明：[数据说明](/Users/lizhexi/Desktop/InternData/ML期货项目Data/数据说明.md)
- 高频特征：[[02_Factors/高频特征工程|高频特征工程]]
- 模型体系：[[03_Model/模型体系|模型体系]]
- LightGBM：[[03_Model/LightGBM模型说明|LightGBM模型说明]]
- 代码说明：[[04_Code/README|Code]]
- 实验记录：[[05_Experiment/experiment_log|Experiment Log]]
- 完整报告：[[06_Report/项目总结报告|项目总结报告]]
- 面试版本：[[06_Report/面试讲解版|面试讲解版]]
- 原始资料：[[07_Reference/README|Reference]]

## 目录结构

```text
202502_ML期货项目/
├── README.md
├── PROJECT_STATUS.md
├── 00_Project_Profile/
├── 01_Research/
├── 02_Factors/
├── 03_Model/
├── 04_Code/
├── 05_Experiment/
├── 06_Report/
└── 07_Reference/
```

项目数据不占用仓库内编号，独立保存在 `/Users/lizhexi/Desktop/InternData/ML期货项目Data`。

## Git 与数据边界

- Notebook 可纳入 Git 版本管理。
- 本项目按个人展示仓库管理，只公开研究说明和代码 Notebook。
- FastBox 原始数据和生成的 Pickle 数据不进入 Git。
- 项目数据统一保存在 `/Users/lizhexi/Desktop/InternData/ML期货项目Data`；可通过环境变量 `ML_FUTURES_DATA_ROOT` 覆盖该位置。
- FastBox 认证信息通过环境变量 `FASTBOX_USERNAME` 和 `FASTBOX_PASSWORD` 提供。
- Commit 与 push 由用户手动执行。
