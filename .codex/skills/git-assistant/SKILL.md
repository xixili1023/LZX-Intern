---
name: git-assistant
description: Generate Chinese-first Git commit information for completed stages of work in the LZX-Intern Personal Quant Research Portfolio. Use when the user wants a commit title, change summary, and purpose without executing Git commands, committing, pushing, staging, or changing Git history.
---

# Git Assistant Skill

## 使用场景

当用户完成一个阶段性修改，希望整理 Git commit 信息时使用。

基于用户提供的修改范围和阶段目标生成说明。若信息不足，指出需要补充的变更内容，不运行 Git 命令获取信息。

## 输出内容

按以下顺序生成：

1. 类型
2. Commit 标题
3. 修改内容摘要
4. 修改目的

修改内容摘要使用简洁列表，只保留能够说明本阶段成果的关键变化。

## Commit 原则

- 一次 Commit 对应一个阶段性工作。
- 围绕一个清晰目的组织 Commit 信息。
- 不记录过于细碎、没有独立意义的修改。
- 不把互不相关的研究、代码、实验和文档变化强行合并。
- 标题准确描述已经完成的工作，不使用含义模糊的表述。
- 只根据已知变化生成内容，不虚构文件、结果或研究进展。

## Commit 语言规范

- 以中文为主。
- 专业术语可以保留英文，例如 Factor、Backtest、Experiment、Git、Commit。
- 不强制使用英文 Commit。
- 标题保持简洁，修改内容和目的使用完整、清楚的中文。

## Commit 分类

- `Research`：研究框架、研究逻辑、因子设计相关修改。
- `Code`：代码新增、修改或优化。
- `Experiment`：实验设计、参数测试、回测结果相关修改。
- `Docs`：README、Markdown 文档、项目说明相关修改。

当一次阶段性工作涉及多个分类时，选择最能代表主要目的的分类；若内容实际上属于多个独立阶段，建议拆分为多个 Commit。

## 输出示例

类型：

Research

Commit 标题：

完善行业轮动因子研究框架

修改内容：

- 补充研究背景
- 完善因子设计逻辑
- 更新项目说明

修改目的：

明确研究路线，为后续因子测试和回测提供基础。

## 限制

- 只生成 Git commit 说明。
- 不执行任何 Git 命令。
- 不执行 stage 或修改暂存区。
- 不执行 commit。
- 不执行 push。
- 不执行 amend、rebase、reset 或其他 Git 历史修改。
- 不代替用户确认最终 Commit 内容。

