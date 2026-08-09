# Data

## 文件夹用途

管理项目专属数据的来源、字段、版本、处理流程和质量说明，建立可追踪的数据血缘。

## 应该存放什么

- `数据说明.md`：来源、许可、频率、范围、字段和质量检查
- `raw/`：项目原始数据的本地入口或必要的小型样例
- `processed/`：处理后数据的本地入口或必要的小型样例
- 数据获取、清洗和重建说明
- 数据版本标识与项目所用快照信息

## 不应该存放什么

- 需要跨项目复用的公共数据；应进入仓库外的 `~/Desktop/InternData/StockData`
- 密钥、账号、访问令牌或受限凭证
- 不允许提交 Git 的大型、敏感或受版权限制的数据
- 没有来源、许可或字段说明的数据文件

## 与其他模块的关系

- 数据需求由 [[01_Research/README|Research]] 决定。
- 数据处理代码位于 [[05_Code/README|Code]] 的 `data/`。
- 为 [[03_Factors/README|Factors]]、[[04_Backtest/README|Backtest]] 和 [[06_Experiment/README|Experiment]] 提供版本化输入。
- [[07_Report/README|Report]] 应引用本模块的数据口径和限制。
