---
name: data-processing
description: Design and document reproducible data acquisition, validation, cleaning, transformation, and versioning workflows for LZX-Intern quant investment, factor research, and strategy backtest projects. Use when working with a project's 02_Data module or 05_Code/data implementation.
---

# Data Processing

## 使用场景

- 设计量化投资项目的数据获取、清洗、转换和验证流程。
- 为因子研究准备截面、时间序列、财务或市场数据。
- 为策略回测建立无前视偏差的数据快照和输入口径。
- 完善 `02_Data` 的数据说明或规划 `05_Code/data` 的处理职责。
- 审查数据质量、数据血缘、版本管理和 Git 存储边界。

## 输入要求

开始前获取或确认：

- 研究问题、样本范围、资产范围、频率和时间口径。
- 数据来源、许可、访问方式、字段、主键、单位和覆盖范围。
- 原始数据与目标数据的格式、规模和存储位置。
- 缺失值、异常值、重复值、停牌、退市和复权等处理要求。
- 目标产物、数据版本规则和下游因子或回测需求。

若数据不可访问，仅设计和记录流程，不假设数据内容。

## 执行流程

1. 检查 `01_Research`、`02_Data`、`05_Code/data` 与 `.gitignore`。
2. 建立数据清单，记录来源、许可、频率、字段和时间可用性。
3. 定义从 `raw` 到 `processed` 的转换顺序及每一步输入输出。
4. 设计缺失、重复、异常、单位、时间戳和主键检查。
5. 检查前视偏差、生存者偏差、样本选择偏差和数据泄漏风险。
6. 为数据快照或处理结果建立可复现版本标识。
7. 将处理逻辑记录在 `02_Data`，将实现职责放在 `05_Code/data`。
8. 验证大型或受限数据不会被 Git 跟踪。

## 输出要求

- 输出数据说明、字段口径、处理流程和质量检查要求。
- 明确原始数据、处理后数据和公共数据的存储位置。
- 记录数据版本、重建方式、下游依赖和已知限制。
- 若执行了获准的数据处理，汇报产物位置与验证结果；否则只输出计划。

## 注意事项

- 未经明确要求不下载、覆盖、移动或删除数据。
- 不提交大型、敏感、受限或包含凭证的数据。
- 不隐瞒人工修正；所有重要转换必须可追踪。
- 项目专属数据进入仓库外的 `~/Desktop/InternData/<项目数据目录>`，跨项目公共数据进入仓库外的 `~/Desktop/InternData/StockData`；仓库内只保留数据说明、代码和必要的小型元数据。
- 不使用未来时点才能获得的信息构造历史样本。
- 不写具体代码，除非用户在后续任务中明确要求实现。
