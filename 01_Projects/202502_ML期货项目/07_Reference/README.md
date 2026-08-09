# Reference

本模块保存原始课程材料和迁移来源说明。

## 原始材料

- [[原始材料/ML期货项目|ML期货项目原始 Markdown]]

原始 Markdown 按来源原样保留，其中可能包含早期的个人贡献、模型清单和特征描述。当前项目的正式口径以整理后的 Profile、Factors、Model 和 Report 文档为准：项目由团队共同完成，只把三个现有 Notebook 中能够确认的内容标记为已实现。

## Notebook 来源与迁移位置

| 原文件 | 迁移位置 |
| --- | --- |
| `ML1_homework.ipynb` | [[../04_Code/01_data_processing/README|数据处理与特征工程]] |
| `Modeling.ipynb` | [[../04_Code/02_model_training/README|模型训练]] |
| `Modeling 1.ipynb` | [[../04_Code/03_backtest/README|策略回测]] |

## 引用状态

原始 Markdown 中的模型原理说明没有提供完整论文或教材引用。为支持 [[LightGBM|LightGBM]]，已补充以下 LightGBM 一手来源：

- Guolin Ke et al., [LightGBM: A Highly Efficient Gradient Boosting Decision Tree](https://papers.nips.cc/paper/6907-lightgbm-a-highly-efficient-gradient-boosting-decision-tree), NeurIPS 2017.
- LightGBM 官方文档：[Features](https://lightgbm.readthedocs.io/en/stable/Features.html)。
- LightGBM 官方文档：[Parameters](https://lightgbm.readthedocs.io/en/stable/Parameters.html)。
- LightGBM 官方文档：[Parameters Tuning](https://lightgbm.readthedocs.io/en/stable/Parameters-Tuning.html)。

Hurst、OFI 等其他方法的正式来源仍待后续研究完善。
