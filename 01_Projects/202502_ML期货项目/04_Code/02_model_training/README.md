# 模型训练 Notebook

## 文件

`Modeling.ipynb`

## 作用

- 读取训练集和测试集。
- 训练并评价 Ridge、SVR、Decision Tree 和 LightGBM。
- 输出 MSE、MAE 与 $R^2$。
- 查看 LightGBM 特征重要性并进行一次特征筛选后重训。
- 保存 MLP、SA-GRU 和 Transformer 等探索性神经网络代码。

## 输入

- `Train_data.pkl`
- `Test_data.pkl`

特征通过位置切片 `iloc[:, 2:-3]` 选取，标签取最后一列。

## 输出

- 各模型的内存预测值。
- Notebook 中保存的误差指标输出。
- Ridge 系数与 LightGBM 特征重要性。
- 神经网络训练输出。

代码没有明确持久化模型文件或预测结果文件。

具体指标暂不迁入研究报告，结果位置保留在本 Notebook 的对应输出单元。

## 对应研究文档

- [[../../03_Model/模型体系|模型体系]]
- [[../../03_Model/LightGBM模型说明|LightGBM模型说明]]
- [[../../03_Model/模型评价|模型评价]]

## 注意

- Lasso 仅作为注释候选，不能视为已运行模型。
- 没有发现独立 Linear Regression 或 Random Forest 实现。
- 特征筛选后 LightGBM 重训使用测试集进行 Early Stopping，需后续审查。
