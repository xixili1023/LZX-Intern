# Quant Research Project

> 使用说明：复制整个 `Project_Template` 到 `01_Projects` 后重命名，再在副本中开展研究。模板本身不填写项目内容。

## 项目模板用途

这是标准 Quant Research Project 的总入口，用于统一组织研究文档、数据说明、因子设计、回测、代码、实验记录、项目状态、参考资料和最终输出。

模板同时支持：

- **Obsidian**：Markdown 文档与 `[[双向链接]]`。
- **VS Code**：模块化代码目录与项目内开发。
- **GitHub**：源代码、文档和代码版本的管理。
- **实验追踪**：研究假设、实验参数、数据范围、方法、结果和结论可追溯。
- **汇报输出**：从完整研究报告到实习、面试展示版本。

## 项目管理文件

| 文件 | 作用 | Obsidian 入口 |
| --- | --- | --- |
| `README.md` | 长期稳定地说明“项目是什么”，包括项目定位、结构、运行方式和导航。 | 当前文件 |
| `PROJECT_STATUS.md` | 动态说明“项目现在进行到哪里”：状态与阶段维护在笔记属性中，正文维护已完成、进行中、下一步计划和最后更新时间。 | [[PROJECT_STATUS\|Project Status]] |
| `06_Experiment/experiment_log.md` | 记录研究过程中做过哪些实验、实验条件、实验结果和结论。 | [[06_Experiment/experiment_log\|Experiment Log]] |
| Git | 负责代码版本管理，保留实现变化和对应 commit。 | Git 历史 |

`README.md` 负责长期稳定说明；`PROJECT_STATUS.md` 负责动态状态管理；`experiment_log.md` 负责研究实验过程；Git 负责代码版本。模板不创建 `CHANGELOG.md`。

## 模块导航

| 模块 | 主要职责 | Obsidian 入口 |
| --- | --- | --- |
| `00_Project_Profile` | 项目定位、背景、个人贡献和时间线。 | [[00_Project_Profile/README\|Project Profile]] |
| `01_Research` | 研究问题、研究框架和方法设计。 | [[01_Research/README\|Research]] |
| `02_Data` | 项目数据来源、口径、处理和质量说明。 | [[02_Data/README\|Data]] |
| `03_Factors` | 因子逻辑、构建过程和评价结果。 | [[03_Factors/README\|Factors]] |
| `04_Backtest` | 回测框架、参数、约束和结果产物。 | [[04_Backtest/README\|Backtest]] |
| `05_Code` | 数据、因子、模型、回测和工具代码。 | [[05_Code/README\|Code]] |
| `06_Experiment` | 参数测试、因子组合、回测方案比较和模型迭代记录。 | [[06_Experiment/README\|Experiment]] |
| `07_Report` | 完整报告及不同场景的汇报版本。 | [[07_Report/README\|Report]] |
| `08_Reference` | 项目专属论文、资料和引用记录。 | [[08_Reference/README\|Reference]] |

## 项目级应该存放什么

- 项目专属的研究文档、代码、配置和小型元数据
- 数据来源、版本与重建说明
- 可复现的研究实验、回测结果和代码版本
- 项目报告、展示稿和面试讲解材料
- 指向公共资产的链接，例如 [[02_Assets/README|Assets]]

## 项目级不应该存放什么

- 密钥、凭证和个人敏感信息
- 不允许公开或提交的大型原始数据
- 缓存、临时文件、虚拟环境和可重建产物
- 与本项目无关的学习笔记或公共工具
- 直接修改后仍作为模板使用的具体研究内容

## 推荐研究链路

`Project Profile` → `Research` → `Data` → `Factors` → `Backtest` → `Experiment` → `Report`

`Code` 支撑数据、因子、回测和实验；`Reference` 为研究逻辑与方法提供依据。各模块通过相对链接或 `[[双向链接]]` 相互关联。

## Git 与复现约定

- 提交 Markdown、源代码、配置、小型图表和复现说明。
- 不提交大型数据、临时文件、运行缓存和本地环境。
- 每次关键实验在 `experiment_log.md` 中记录实验 ID、数据范围、参数、方法、结果与结论，并关联对应 Git commit。
- README 中维护环境安装、运行顺序和主要入口。
