# LightGBM 模型说明

## 说明边界

本项目没有重新实现 LightGBM 算法，而是通过 Python 的 `lightgbm` 库调用 `lgb.train`。以下流程依据迁移后的 Notebook 实际代码说明。

## 完整调用流程

```text
Train_data.pkl / Test_data.pkl
        ↓
选取特征列与未来收益标签
        ↓
训练集 / 验证集划分
        ↓
lgb.Dataset 数据封装
        ↓
直方图分桶与 Leaf-wise 决策树构建
        ↓
GBDT Boosting 顺序迭代
        ↓
Early Stopping 选择 best_iteration
        ↓
测试集预测
        ↓
MSE / MAE / R² 与 Feature Importance
        ↓
预测阈值转化为回测信号
```

## 1. 数据输入

模型 Notebook 读取：

- `Train_data.pkl`
- `Test_data.pkl`

实际代码以 `iloc[:, 2:-3]` 作为特征，以最后一列作为标签。训练数据进一步使用 `train_test_split(test_size=0.1, random_state=42)` 划分训练与验证部分。

回测 Notebook 中另有一个 LightGBM 版本，在训练集上使用 `KFold(n_splits=5, shuffle=True, random_state=42)`，对五个模型的测试集预测取平均。

## 2. 特征处理

特征的清洗、派生和按日扩展窗口标准化在数据处理 Notebook 中完成。LightGBM 训练前没有再次进行标准化。

模型 Notebook 调用：

```text
bst.feature_importance()
```

并在一次后续训练中保留重要性不低于 5 的特征，再次训练模型。该重要性为库函数默认口径，代码没有明确改为 gain，因此需要按默认 split importance 理解。

这一步是已有代码行为，不代表已完成稳健的特征选择验证。

## 3. 决策树构建

LightGBM 将连续特征离散到直方图桶中，通过桶内梯度统计寻找分裂点，并采用 Leaf-wise 策略优先分裂能够带来最大损失下降的叶节点。

本项目没有手写分裂算法；树结构由 `lgb.train` 根据输入数据和参数自动生成。

## 4. Boosting 迭代

模型使用：

- `boosting_type='gbdt'`
- `objective='regression'`
- `metric='rmse'`

每轮新增一棵树拟合当前误差，最终预测是多棵树输出的加总。训练最多运行 100 轮，并使用 5 轮 Early Stopping 选择 `best_iteration`。

## 5. 预测输出

代码使用：

```text
bst.predict(X_test, num_iteration=bst.best_iteration)
```

得到测试集未来收益预测，再计算 MSE、MAE 和 $R^2$。回测 Notebook 将预测值与正负阈值比较，生成多空信号。

## 实际参数解释

| 参数概念 | 实际代码 | 本项目含义 |
| --- | --- | --- |
| `n_estimators` | 未使用 sklearn API 的该参数；实际为 `num_round=100` | 最多构建 100 轮 Boosting 树，Early Stopping 可提前停止 |
| `learning_rate` | `0.01` | 控制每棵新增树对总预测的贡献 |
| `max_depth` | 未显式设置 | 代码没有直接限制最大深度，复杂度主要由 `num_leaves` 等参数控制 |
| `num_leaves` | `31` | 限制单棵树的叶节点数量 |
| `feature importance` | `bst.feature_importance()` | 输出特征参与分裂的重要性；一次实验用阈值 `>=5` 选择特征 |

其他实际参数：

| 参数 | 值 | 作用 |
| --- | --- | --- |
| `feature_fraction` | `0.9` | 每轮使用部分特征 |
| `bagging_fraction` | `0.8` | 对训练样本进行子采样 |
| `bagging_freq` | `5` | 每 5 轮执行一次 Bagging |
| Early Stopping | 5 轮 | 验证指标连续 5 轮不改善则停止 |

## 需要审查的问题

1. `max_depth` 未设置，Leaf-wise 生长可能产生较深的树。
2. 模型训练 Notebook 的特征筛选后重训版本把测试集作为 `valid_sets`，可能将测试信息用于 Early Stopping。
3. 回测 Notebook 的 `KFold(shuffle=True)` 不保持时间顺序。
4. 特征重要性阈值 5 的选择依据没有实验记录。
5. 正式标签使用未来 3 秒 `last_price return`；`D_k`、`effective_spread` 和部分 `avg_price` 记录依赖当前 `last_price`，需要审查其时间可用性。

这些问题只做记录，本次迁移没有修改模型代码或已有输出。
