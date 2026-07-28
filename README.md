# Personal Quant Research Portfolio

这是一个长期沉淀个人量化研究项目、代码、数据、实验记录和面试材料的研究资产库，同时作为 Obsidian Vault、VS Code Workspace 和 GitHub Repository 使用。

## 核心原则

1. **项目是核心主体**：每项研究经历或策略研究都在 `01_Projects` 中独立组织。
2. **公共资产与项目分离**：跨项目复用的数据、代码和参考资料统一进入 `02_Assets`。
3. **模板只用于复制**：所有模板集中在 `03_Templates`，不直接在模板内开展项目。
4. **学习与项目输出分离**：知识笔记进入 `04_Learning`；报告、汇报和面试材料保存在来源项目的 `07_Report`。
5. **研究过程可追踪**：项目中的研究逻辑、数据、代码、实验和报告相互链接，并通过 Git 保留版本。

## 目录导航

| 目录 | 作用 | Obsidian 入口 |
| --- | --- | --- |
| `00_Home` | Portfolio 首页、导航与索引。 | [[00_Home/首页\|首页]] |
| `01_Projects` | 独立量化研究项目，是本资产库的核心。 | [[01_Projects/README\|Projects]] |
| `02_Assets` | 多项目共享的数据、代码和参考资料。 | [[02_Assets/README\|Assets]] |
| `03_Templates` | 新项目、因子、回测和报告模板。 | [[03_Templates/README\|Templates]] |
| `04_Learning` | Python、量化、统计、机器学习和面试学习笔记。 | [[04_Learning/README\|Learning]] |
| `.codex` | Codex 工作约定、研究配置与本地技能。 | 代码配置目录 |
| `.obsidian` | Obsidian Vault 配置。 | Obsidian 配置目录 |

## 推荐工作流

1. 从 [[00_Home/首页|首页]] 进入研究资产库。
2. 从 [[03_Templates/README|Templates]] 复制所需模板。
3. 在 `01_Projects` 下创建独立项目，并在项目内维护完整研究链路。
4. 只把真正跨项目复用的内容沉淀到 [[02_Assets/README|Assets]]。
5. 将学习笔记归档到 [[04_Learning/README|Learning]]；将完整报告、实习汇报、面试材料和研究展示版本保存在对应项目的 `07_Report`。

## 项目输出约定

- 研究报告、实习汇报、面试材料和展示版本都属于具体项目，不设独立的顶层报告目录。
- 每个项目通过 `07_Report/README.md` 管理输出，并回链研究、数据、因子、回测和实验记录。
- 通用报告模板和输出说明位于 [[03_Templates/Research_Report_Template/README|Research Report Template]]。

## Git 管理约定

- 跟踪 Markdown、源代码、配置、小型元数据和复现说明。
- 不提交大型原始数据、敏感数据、密钥、缓存、临时文件或可重建产物。
- 数据目录通过 README 记录来源、版本、许可和重建方式。
- 项目代码、实验参数和研究结论应通过 Git commit 保持可追溯。
