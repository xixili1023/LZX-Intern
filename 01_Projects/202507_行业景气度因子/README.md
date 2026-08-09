# 202507_行业景气度因子

> 项目状态：已完成

## 项目说明

这是行业景气度因子研究项目，采用标准 Quant Research Project 结构，用于统一组织研究文档、数据说明、因子设计、回测、代码、实验记录、项目状态、参考资料和最终输出。

项目来源于实习期间开展的行业轮动研究。原始研究以申万一级行业指数和动态龙头股池为研究对象，结合短中期情绪/动量信号与中长期行业景气度信号，并对因子评价、信号组合、交易回测和对冲表现进行分析。

## 原始资料迁移说明

- 原始文档：`MY行业项目 .md`
- 本次迁移仅重组原文已有信息，没有新增数据、代码或回测结果。
- 原始文档继续作为迁移依据；项目内各模块是后续维护入口。

## 项目管理文件

| 文件                                | 作用                                    | Obsidian 入口                                      |
| --------------------------------- | ------------------------------------- | ------------------------------------------------ |
| `README.md`                       | 长期稳定地说明“项目是什么”，包括项目定位、结构、运行方式和导航。     | 当前文件                                             |
| `PROJECT_STATUS.md`               | 动态说明“项目现在进行到哪里”，维护状态、阶段、任务、计划和最后更新时间。 | [[PROJECT_STATUS\|Project Status]]               |
| `05_Experiment/experiment_log.md` | 记录研究过程中做过哪些实验、实验条件、实验结果和结论。           | [[05_Experiment/experiment_log\|Experiment Log]] |
| Git                               | 负责代码版本管理，保留实现变化和对应 commit。            | Git 历史                                           |

`README.md` 负责长期稳定说明；`PROJECT_STATUS.md` 负责动态状态管理；`experiment_log.md` 负责研究实验过程；Git 负责代码版本。模板不创建 `CHANGELOG.md`。

## 模块导航

| 模块 | 主要职责 | Obsidian 入口 |
| --- | --- | --- |
| `00_Project_Profile` | 项目定位、背景、个人贡献和时间线。 | [[00_Project_Profile/README\|Project Profile]] |
| `01_Research` | 研究问题、研究框架和方法设计。 | [[01_Research/README\|Research]] |
| 外部数据目录 | 数据来源、口径、处理和质量说明，不纳入 Git 仓库。 | [行业景气度项目Data](/Users/lizhexi/Desktop/InternData/行业景气度项目Data/README.md) |
| `02_Factors` | 因子逻辑、构建过程和评价结果。 | [[02_Factors/README\|Factors]] |
| `03_Backtest` | 回测框架、参数、约束和结果产物。 | [[03_Backtest/README\|Backtest]] |
| `04_Code` | 数据、因子、模型、回测和工具代码。 | [[04_Code/README\|Code]] |
| `05_Experiment` | 参数测试、因子组合、回测方案比较和模型迭代记录。 | [[05_Experiment/README\|Experiment]] |
| `06_Report` | 完整报告及不同场景的汇报版本。 | [[06_Report/README\|Report]] |
| `07_Reference` | 项目专属论文、资料和引用记录。 | [[07_Reference/README\|Reference]] |

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
- 与本项目无关的具体研究内容

## 推荐研究链路

`Project Profile` → `Research` → `External Data` → `Factors` → `Backtest` → `Experiment` → `Report`

`Code` 支撑数据、因子、回测和实验；`Reference` 为研究逻辑与方法提供依据。各模块通过相对链接或 `[[双向链接]]` 相互关联。

项目内容入口：

- [[00_Project_Profile/项目简介|项目简介]]
- [[01_Research/项目建设路线图|从零重建路线图]]
- [[01_Research/研究框架|研究框架]]
- [数据说明](/Users/lizhexi/Desktop/InternData/行业景气度项目Data/数据说明.md)
- [[02_Factors/README|因子体系]]
- [[03_Backtest/回测框架|回测框架]]
- [[05_Experiment/experiment_log|Experiment Log]]
- [[06_Report/完整研究报告|完整研究报告]]
- [[06_Report/面试讲解版|面试讲解版]]

## Git 与复现约定

- 提交 Markdown、源代码、配置、小型图表和复现说明。
- 不提交大型数据、临时文件、运行缓存和本地环境。
- 项目数据统一保存在 `/Users/lizhexi/Desktop/InternData/行业景气度项目Data`；可通过环境变量 `INDUSTRY_PROJECT_DATA_ROOT` 覆盖该位置。
- 每次关键实验在 `experiment_log.md` 中记录实验 ID、数据范围、参数、方法、结果与结论，并关联对应 Git commit。
- README 中维护环境安装、运行顺序和主要入口。
