# Code

本模块同时保存原始课程版本与研究级优化版本。原始 Notebook 用于追溯，revised Notebook 用于后续可复现研究。

## 版本入口

| 目录 | 定位 | 修改规则 |
| --- | --- | --- |
| [[original/README|original]] | 三个原始 Notebook 的冻结副本 | 不直接修改 |
| [[revised/README|revised]] | 时间序列、模型验证与回测优化版本 | 后续研究入口 |

## 原职责分类目录

| 模块 | Notebook | 职责 |
| --- | --- | --- |
| [[01_data_processing/README|数据处理与特征工程]] | `ML1_homework.ipynb` | 数据获取、清洗、特征构造、标准化与样本划分 |
| [[02_model_training/README|模型训练]] | `Modeling.ipynb` | 模型训练、预测误差评价与探索性神经网络 |
| [[03_backtest/README|策略回测]] | `Modeling_Backtest.ipynb` | 信号生成、成本敏感性、模型回测与结果比较 |

这些目录保留原迁移文件与既有 Obsidian 链接。其 Notebook 与 `original/` 对应文件一致，不作为新版代码入口。

## 运行依赖

Notebook 中可以确认的主要依赖包括：

- Python、NumPy、pandas；
- FastBox；
- scikit-learn；
- LightGBM；
- SciPy、joblib；
- Matplotlib；
- PyTorch。

完整环境版本未在原项目中固定，当前没有生成新的依赖锁定文件。

## 数据与凭证

- `features.pkl` 来源于已有数据处理流程；它与 `Train_data.pkl`、`Test_data.pkl` 均不进入 Git。
- FastBox 登录信息通过 `FASTBOX_USERNAME` 和 `FASTBOX_PASSWORD` 环境变量提供。
- 原 Notebook 中的硬编码凭证已从迁移副本移除；这是唯一的代码内容安全调整，不改变计算逻辑。

## Revised运行顺序与缺口

预期顺序为：

1. `revised/ML1_homework.ipynb`
2. `revised/Modeling.ipynb`
3. `revised/Modeling_Backtest.ipynb`

数据处理 Notebook 会读取由已有数据处理流程生成的 `features.pkl`，并要求另行提供真实交易日历 `trading_calendar.csv`。上游生成流程和交易日历文件均不在本次三个 Notebook 中。

Test 默认锁定。应先完成 Validation 研究并冻结特征、参数和信号阈值，再进行一次最终 Test 评价。
