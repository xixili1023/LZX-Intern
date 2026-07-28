---
name: research-document
description: Structure, edit, and maintain traceable Markdown research documents for quant investment, factor research, and strategy backtest projects in LZX-Intern. Use for research questions, frameworks, methods, hypotheses, decisions, limitations, and Obsidian links within a project's 01_Research module.
---

# Research Document

## 使用场景

- 建立或完善项目的研究问题、研究框架和方法说明。
- 将量化投资想法整理为可检验的研究假设。
- 为因子研究记录经济逻辑、变量定义和验证设计。
- 为策略回测记录研究边界、基准、方法选择与限制。
- 整理已有研究材料，使其可在 Obsidian 中双向导航并在 GitHub 中审阅。

## 输入要求

优先读取并确认：

- 项目的 `00_Project_Profile` 和 `01_Research` 现有文档。
- 用户明确提供的研究目标、研究对象、样本范围和时间范围。
- 可检验假设、评价标准、数据可得性与研究约束。
- 已有数据、因子、回测、实验和参考资料的路径或链接。
- 需要新建、重构、补充还是审阅文档。

缺少证据时标记为待确认，不得把假设写成事实。

## 执行流程

1. 检查项目结构、现有术语、文档状态和 Git 变更。
2. 区分研究问题、子问题、假设、方法、假设条件、决策和局限。
3. 将研究问题设计为可由数据、因子评价或策略回测检验的形式。
4. 记录方法选择理由、备选方法和关键口径。
5. 使用 `[[双向链接]]` 连接 `02_Data`、`03_Factors`、`04_Backtest`、`06_Experiment`、`07_Report` 和 `08_Reference`。
6. 明确事实、用户陈述、推断、假设和未解决问题的边界。
7. 检查 Markdown 层级、Obsidian 链接与 GitHub 可读性。

## 输出要求

- 输出结构清晰、可追踪的 Markdown 研究文档。
- 保留从研究问题到数据、方法、实验和报告的证据链。
- 明确列出假设条件、评价标准、限制和待确认事项。
- 汇报更新文件、主要结构调整、链接变化和证据缺口。

## 注意事项

- 不虚构引用、研究背景、数据可用性、实验结果或项目历史。
- 不擅自改变用户的研究目标或方法口径。
- 不用结论性语言描述未经验证的研究假设。
- 不以代码或结果截图替代研究逻辑说明。
- 未经要求不运行代码、不处理数据、不执行回测。
- 保留用户已有内容；遇到矛盾时标注并说明，不静默改写。

