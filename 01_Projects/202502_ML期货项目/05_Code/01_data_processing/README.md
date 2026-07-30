# 数据处理与特征工程 Notebook

## 文件

`ML1_homework.ipynb`

## 作用

- 登录 FastBox 并读取 `CU2311` 半秒级 Level-2 数据。
- 重建交易时段内的 500 毫秒时间轴。
- 处理缺失、重复和异常价格。
- 构造盘口、订单流与 Hurst 特征。
- 对特征按交易日进行扩展窗口标准化。
- 生成训练集和测试集 Pickle 文件。

## 输入

- FastBox 数据访问权限。
- 环境变量 `FASTBOX_USERNAME`。
- 环境变量 `FASTBOX_PASSWORD`。
- Notebook 后半部分依赖由已有数据处理流程生成的 `features.pkl`。

## 输出

- 内存中的清洗数据和高频特征。
- `Train_data.pkl`。
- `Test_data.pkl`。
- 描述统计和图形输出。

`features.pkl` 的生成属于已有数据处理流程，不在本次三个 Notebook 内重复实现。

## 对应研究文档

- [[../../02_Data/数据处理流程|数据处理流程]]
- [[../../03_Factors/高频特征工程|高频特征工程]]

## 迁移说明

原 Notebook 的硬编码 FastBox 登录凭证已改为环境变量读取；其他代码单元和已有输出未修改。
