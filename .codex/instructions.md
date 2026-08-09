# Codex Workspace Instructions

## Scope

本仓库是 Personal Quant Research Portfolio，同时服务于 Obsidian、VS Code 和 GitHub。

## Working Rules

1. 保持 `00_Home` 至 `04_Learning` 的顶层结构稳定，项目是核心主体。
2. 新研究项目从 `03_Templates/Project_Template` 复制到 `01_Projects`。
3. 不在模板中写入具体研究内容。
4. 每个项目独立保存项目介绍、研究逻辑、数据说明、因子设计、回测框架、代码、实验记录和报告总结。
5. 跨项目共享数据进入仓库外的 `~/Desktop/InternData/StockData`；项目专属数据进入仓库外的 `~/Desktop/InternData/<项目数据目录>`；共享代码和参考资料进入 `02_Assets/Code` 或 `02_Assets/References`。
6. 学习笔记进入 `04_Learning`；研究报告、实习汇报、面试材料和展示版本保存在对应项目的 `07_Report`。
7. 研究结论必须能够追溯到研究文档、代码版本、数据版本和实验记录。
8. 不提交密钥、凭证、敏感数据、大型数据、缓存、临时文件或可重建产物。
9. 修改现有文件前先检查上下文，避免覆盖或删除用户内容。
10. 文档优先使用 Markdown；内部导航优先使用 Obsidian `[[双向链接]]`，同时保持 GitHub 可读。
11. 仓库文档面向研究协作与专业审阅，只记录与项目研究、进度和交付有关的信息。
12. `PROJECT_STATUS.md` 中的任务条用于展示已完成里程碑、当前研究工作、下一阶段计划和待确认事项，并应尽可能链接到研究证据。

## Git Version Management

GitHub 用于保存项目版本、展示研究过程并方便带教查看项目演进。

- Git commit 和 push 必须由用户手动执行。
- Codex 不自动 commit，不自动 push，不修改 Git 历史。
- 未经用户明确要求，Codex 不执行 stage 或修改暂存区。
- Codex 可以整理 Commit 标题、修改内容摘要和修改目的，供用户审核后手动使用。
- 使用 `git-assistant` 时只生成说明，不执行任何 Git 命令。
- 不执行 amend、rebase、reset 或其他会改写 Git 历史的操作。

## Project Minimum

每个项目至少维护：

- 项目介绍与个人贡献
- 研究问题、框架和方法
- 数据说明
- 因子或模型设计
- 回测框架与参数
- 项目代码
- 实验记录
- 完整报告与展示版本
