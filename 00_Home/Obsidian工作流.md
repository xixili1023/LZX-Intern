# Obsidian 工作流

本页说明 Personal Quant Research Portfolio 的 Obsidian 插件分工和推荐配置。Obsidian、VS Code 与 GitHub 始终使用同一个仓库目录，不复制 Vault，不建立第二套项目目录。

## 工作目录

统一目录：

```text
/Users/lizhexi/Desktop/LZX-Intern
```

- Obsidian：将该目录作为 Vault 打开。
- VS Code：使用“打开文件夹”打开该目录。
- Git/GitHub：在该目录中查看变更并由用户手动 commit、push。
- Markdown、代码和配置始终只有一份；`.obsidian` 只保存 Obsidian 的界面与插件配置。

## 插件分工

| 插件 | 负责内容 | 不负责内容 |
| --- | --- | --- |
| Dataview | 自动展示项目 metadata | 修改项目状态或生成研究结论 |
| Tasks | 汇总可执行任务 | 保存方法、结论和数据定义 |
| QuickAdd | 创建标准项目和实验记录 | 替代项目模板或自动编造实验内容 |
| Excalidraw | 表达复杂关系和流程 | 保存精确参数、结果和结论 |
| Outliner | 编辑长文提纲和嵌套列表 | 把所有报告改成列表 |
| Notebook Navigator | 项目和首页快速导航 | 项目数据库计算 |

## Dataview

入口：[[00_Home/项目数据库|项目数据库]]。

项目 metadata 统一保存在 `01_Projects/<项目>/PROJECT_STATUS.md`。Dataview 只读查询这些字段，因此在 VS Code 和 GitHub 中仍然是普通 YAML 与 Markdown。

每个项目只维护五个必需属性：

```yaml
---
project_status: "进行中"
current_stage: "因子测试"
project_type: "因子研究"
frequency: "日频"
method: "因子构建"
---
```

项目名称直接使用目录名，创建时间直接使用项目目录前缀，不再建立重复属性。

- `frequency`：最终研究、信号或回测的主要频率，例如 `高频`、`日频`、`周频`、`月频`。
- `method`：只填写最能代表项目的一种主要方法，例如 `因子构建`、`机器学习`、`LightGBM`、`组合优化`、`回测`。
- 原始数据可能同时包含多个频率，具体情况写在 `02_Data`，不全部堆进项目属性。
- 具体模型、参数和辅助方法写在研究或模型文档，不全部堆进 `method`。

### 标签规则

标签只用于“无法从目录或项目属性判断、并且值得跨项目检索”的研究主题。

- 每个项目最多 `0–2` 个标签。
- 标签只放在项目的 `PROJECT_STATUS.md`。
- 不给首页、模板、任务、实验记录和普通项目文档加标签。
- 不使用 `quant-research`、`factor-research`、`machine-learning`、`home`、`experiment`、`task` 等重复标签。

当前两个项目都不需要标签。只有以后出现多个项目共享同一主题，并且确实需要跨项目筛选时，才给这些项目添加同一个标签。例如出现两个以上行业轮动项目时再使用 `industry-rotation`。

## Tasks

入口：[[00_Home/当前任务|当前任务]]。

推荐将阶段行动放在项目 `PROJECT_STATUS.md`，将实验产生的后续行动放在对应实验记录。任务统一使用 Markdown 复选框，日期通过 Tasks 的创建或编辑窗口添加。

## QuickAdd

QuickAdd 是 Obsidian 内的“固定表单创建器”，不理解“请帮我创建一个名为 XXX 的项目”这样的自然语言。两种创建入口分别是：

- 对 Codex 说“请帮我创建一个新的量化研究项目，名字是 XXX”：由 Codex 检查仓库并按标准模板创建。
- 在 Obsidian 中运行 QuickAdd 的 `新建量化项目`：按表单选择六项信息后，由本地脚本复制标准模板。

两种入口使用同一个 `Project_Template`，最终都创建在 `01_Projects`，不要混用第二套目录。

### 基础设置

在 `设置 → QuickAdd` 中：

1. 将 Template folder 设为 `03_Templates`。
2. 保持 Disable AI & Online features 开启；本工作流不依赖 QuickAdd AI。
3. 建议开启 One-page input form，便于一次填写实验模板中的多个字段。

### 快速创建完整项目

QuickAdd 的普通 Template Choice 只能创建单个文件，不能复制完整项目目录。因此项目创建使用 User Script 复制现有 `Project_Template`：

1. 在 QuickAdd 中新建一个 `Macro`，名称设为 `新建量化项目`。
2. 打开 Macro Builder，添加 `User Script`。
3. 选择 `Create_Project`，来源是：
   `03_Templates/QuickAdd_Scripts/Create_Project.js`。
4. 将该 Macro 加到命令面板，并按需要绑定快捷键。

运行后依次选择项目目录、项目类型、项目状态、当前阶段、研究频率和主要方法。脚本会：

1. 检查目标项目目录是否已存在。
2. 将完整的 `03_Templates/Project_Template` 复制到 `01_Projects/<项目目录>`。
3. 使用 `Project_Create_Template.md` 生成新项目的 `PROJECT_STATUS.md`。
4. 打开新项目 README。

脚本只创建新目录；若目标目录已经存在会立即停止，不覆盖已有项目。

### 快速创建实验记录

在 QuickAdd 中新增 `Template` Choice：

| 设置 | 值 |
| --- | --- |
| Choice 名称 | `新建实验记录` |
| Template Path | `03_Templates/Experiment_Create_Template.md` |
| File Name Format | `01_Projects/{{VALUE:project_folder}}/06_Experiment/{{VALUE:experiment_id}}_{{VALUE:experiment_name}}` |
| Create in folder | 关闭 |
| Open created file | 开启 |
| File exists | Do nothing 或 Increment file name |

运行时填写：

- `project_folder`：实际项目目录名
- `experiment_id`：例如 `EXP_001`
- `experiment_name`：简短实验名称

模板不会预填实验结果；运行完成后再根据真实证据填写结果、结论和限制。

## Excalidraw

默认绘图目录规划为 `02_Assets/Excalidraw`。详细边界见 [[02_Assets/Excalidraw/README|Excalidraw 绘图规范]]。

适合：

- 研究框架图
- 模型流程图
- 因子逻辑图
- 回测流程图

不建议为每篇笔记配图，也不批量生成图片。参数、评价结果和研究结论继续写在 Markdown 中。

## Outliner

推荐用于长 Markdown 报告的“提纲阶段”：

1. 用嵌套列表拆解章节、论点、证据和待补材料。
2. 使用 Tab / Shift+Tab 调整层级，移动时保持整个子树一起移动。
3. 开启缩进参考线和列表折叠，方便管理长提纲。
4. 结构稳定后，将正式内容展开为 Markdown 标题、段落和表格。

推荐结构：

```markdown
- 研究问题
  - 核心假设
    - 支持证据
    - 反例与限制
  - 验证方法
    - 数据
    - 因子或模型
    - 回测
```

任务和知识内容应分开：

```markdown
- 研究判断：景气度信号可能提供中长期信息
- [ ] 检验景气度信号的滚动稳定性
```

Tasks 不需要 `#task` 标签，只根据复选框识别任务。

### 关于 `TQ_*` 属性

Tasks 8.3 会自动向 Obsidian 登记一组 `TQ_*` 高级查询属性。它们用于控制任务查询页面的显示方式，当前使用次数都是 `0`：

- 不是项目属性；
- 不是任务标签；
- 不会进入项目数据库；
- 不需要填写或理解。

Tasks 每次启动都会重新登记这些名称，因此保留 Tasks 功能时无法通过删除配置永久移除。建议关闭“所有属性”侧栏；需要查看当前笔记属性时，只看笔记顶部实际出现的五个项目属性。

## Notebook Navigator

推荐配置：

| 设置 | 推荐值 |
| --- | --- |
| Start view | Files |
| Layout | Dual pane |
| Folder sort | Name ascending |
| Note sort | Modified descending |
| Auto reveal active file | On |
| Include descendant notes | Off |
| Recent notes | On，5 条 |
| Homepage | `00_Home/首页.md` |

推荐快捷入口不超过 5 个：

1. `00_Home/首页.md`
2. `00_Home/项目数据库.md`
3. `00_Home/当前任务.md`
4. `00_Home/研究地图.md`
5. `03_Templates/README.md`

顶层目录已经使用 `00_` 至 `04_` 编号，因此保持名称升序即可，不需要手工拖动或重排目录。

管理长报告时，在 Notebook Navigator 中定位项目的 `07_Report`，在 Obsidian Outline 核心插件中查看标题结构，再使用 Outliner 调整尚未定稿的列表提纲。

## 日常使用顺序

### 新项目启动

1. 通过 Codex 或 QuickAdd 创建项目。
2. 在项目 `README.md` 写清项目定位、研究对象和最终交付物。
3. 在 `01_Research` 写研究问题、假设和验证标准。
4. 检查 `PROJECT_STATUS.md` 的五个属性，并只保留近期可执行任务。
5. 在开始写代码前，先在 `02_Data` 记录数据来源、时间范围、频率和可得性。

### 研究执行

1. 从 [[00_Home/项目数据库|项目数据库]] 查看所有项目，只选择一个当前主项目。
2. 从 [[00_Home/当前任务|当前任务]] 选择下一项可验证行动。
3. 按 `Research → Data → Factors/Model → Backtest → Experiment → Report` 推进。
4. 每次参数、模型、因子或回测方案发生实质变化时，创建一条实验记录。
5. 实验记录保存假设、数据版本、参数、结果、结论和对应 Git commit，不把结果写进 Tag 或项目属性。

### 日常维护

平时只需要维护两个地方：

1. `PROJECT_STATUS.md`：更新 `project_status`、`current_stage`、下一步任务和最后更新时间。`frequency`、`method`、`project_type` 只有研究定义真的改变时才修改。
2. 当前实验记录：补充实际参数、结果、结论和限制。

阶段完成后，在 VS Code 中检查代码和 Markdown，再检查 Git 差异并由用户手动 commit、push。不要为了“保持最新”而重复改 README；README 只在项目定位、运行入口或目录结构发生稳定变化时更新。
