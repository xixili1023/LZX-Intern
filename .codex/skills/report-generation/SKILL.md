---
name: report-generation
description: Produce or refine project-grounded Markdown research reports, internship summaries, interview explanations, and portfolio presentations for LZX-Intern quant investment, factor research, and strategy backtest projects. Use when converting project evidence into outputs under 07_Report.
---

# Report Generation

## 使用场景

- 将量化投资项目整理为完整研究报告。
- 将因子研究与策略回测证据提炼为实习汇报版本。
- 为面试准备项目讲解、个人贡献、技术决策和追问材料。
- 为 Personal Quant Research Portfolio 形成可展示的项目版本。
- 审阅报告中的结论是否能够回溯到研究、数据、代码和实验。

## 输入要求

开始前确认：

- 报告类型、目标读者、篇幅、语言和交付格式。
- `00_Project_Profile` 中的项目背景、范围和个人贡献。
- `01_Research` 至 `06_Experiment` 的研究证据与版本信息。
- `08_Reference` 中的引用来源。
- 可以公开、需要匿名化或不得披露的内容边界。
- 已知局限、失败实验、风险和仍待验证事项。

若证据不足，应请求补充或保留明确占位，不编造完整叙事。

## 执行流程

1. 检查项目各模块、现有报告和 Git 状态。
2. 选择完整研究报告、实习汇报、面试讲解或展示版本。
3. 建立“问题—方法—数据—因子或策略—回测—实验—结论”的叙事链。
4. 只使用项目中已有且可核验的事实、指标和结论。
5. 区分个人贡献、协作工作、观察结果、推断、风险和局限。
6. 使用 `[[双向链接]]` 回链来源文档、实验和参考资料。
7. 根据受众调整细节，但不改变事实口径。
8. 检查 Markdown、Obsidian 链接、GitHub 可读性和敏感信息。
9. 将输出保存在对应项目的 `07_Report`。

## 输出要求

- 输出与目标受众匹配的 Markdown 报告或报告结构。
- 所有关键结论、指标和贡献描述都有项目证据来源。
- 明确数据范围、方法、评价标准、风险、局限和复现信息。
- 汇报输出路径、目标读者、引用来源、未解决缺口和省略内容。

## 注意事项

- 不虚构结果、指标、引用、职责、影响或项目经历。
- 不隐瞒失败实验、关键限制或不利结果。
- 不泄露受限数据、密钥、隐私或保密信息。
- 不把项目输出移动到独立的顶层报告目录。
- 未经要求不创建 PPTX、DOCX、PDF 等二进制文件。
- 不执行代码、数据处理或回测来填补报告证据缺口。

