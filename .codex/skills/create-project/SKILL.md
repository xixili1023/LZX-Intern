---
name: create-project
description: Create a new project inside the LZX-Intern Personal Quant Research Portfolio by copying and adapting the standard Project_Template. Use when the user explicitly asks to create, initialize, or scaffold a quant investment, factor research, or strategy backtest project under 01_Projects.
---

# Create Project

## 使用场景

- 用户明确要求创建、初始化或搭建新的量化研究项目。
- 将量化投资、因子研究或策略回测主题转化为标准项目目录。
- 需要从 `03_Templates/Project_Template` 复制结构到 `01_Projects`。
- 需要同步建立 Obsidian 项目入口和 Portfolio 项目索引。

## 输入要求

开始前确认或从现有上下文获得：

- 项目名称与安全的目录名称。
- 项目类型：量化投资、因子研究、策略回测或综合研究。
- 项目当前状态，以及是否需要加入 `00_Home/项目索引.md`。
- 是否只创建空白结构，或允许填写用户明确提供的项目简介。
- 目标目录不存在；如已存在，必须确认是继续完善还是停止。

若缺少研究主题细节，仍可创建空白项目，但不得自行补写研究内容。

创建结果必须包含：

- `README.md`
- `PROJECT_STATUS.md`
- `00_Project_Profile/`
- `01_Research/`
- `02_Data/`
- `03_Factors/`
- `04_Backtest/`
- `05_Code/`
- `06_Experiment/`
- `06_Experiment/experiment_log.md`
- `07_Report/`
- `08_Reference/`

文件职责必须保持清晰：

- `README.md`：说明项目是什么，长期维护项目定位、结构和入口。
- `PROJECT_STATUS.md`：项目状态与当前阶段只写入顶部 YAML 笔记属性；正文只保留已完成事项、进行中事项、下一步计划和最后更新时间。
- `06_Experiment/experiment_log.md`：记录研究实验过程，包括实验目的、参数、结果和结论。
- Git：负责代码、研究文档、配置和必要小型结果文件的版本管理。

## 执行流程

1. 检查 `01_Projects`、`03_Templates/Project_Template`、`.gitignore` 和 Git 状态。
2. 验证目标目录名称，排除路径冲突和覆盖风险。
3. 完整复制项目模板，不直接修改模板源目录。
4. 仅填写用户明确提供的项目身份信息；其余位置保留模板占位。
5. 检查两个根目录文件、`00_Project_Profile` 至 `08_Reference` 和 `06_Experiment/experiment_log.md` 是否完整。
6. 按需在 `00_Home/项目索引.md` 中加入项目 README 的 `[[双向链接]]`。
7. 确认没有创建 `CHANGELOG.md`。
8. 检查 Markdown 链接、空目录占位和 `.gitignore` 规则。
9. 报告创建结果，但不自动提交或推送 Git。

## 输出要求

- 在 `01_Projects/<Project_Name>` 生成完整项目骨架。
- 保留适用于 Obsidian、VS Code 和 GitHub 的目录及文档结构。
- 明确报告项目路径、模板来源、索引变化和验证结果。
- 列出仍需用户补充的项目字段，不用虚构内容填满。

## 注意事项

- 只有用户明确要求时才创建项目。
- 不编造研究问题、因子逻辑、数据、实验、绩效或结论。
- 不覆盖同名目录，不删除现有项目文件。
- 不下载数据、不运行研究、不执行回测。
- 不自动 commit、push 或创建远程仓库。
- 禁止创建 `CHANGELOG.md`；项目历史由 Git 版本管理。
- 项目专属内容留在项目内；公共资产进入 `02_Assets`。
