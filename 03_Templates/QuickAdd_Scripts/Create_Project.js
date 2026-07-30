/**
 * QuickAdd User Script
 *
 * Copies the complete Project_Template into 01_Projects and fills the new
 * PROJECT_STATUS.md from Project_Create_Template.md.
 */
module.exports = async (params) => {
  const { app, quickAddApi, variables } = params;
  const adapter = app.vault.adapter;

  const projectFolder = await quickAddApi.inputPrompt(
    "项目目录",
    "例如：202608_新项目"
  );
  if (!projectFolder) {
    params.abort?.("已取消创建项目");
    return;
  }

  const normalizedFolder = projectFolder.trim();
  if (
    normalizedFolder.includes("/") ||
    normalizedFolder.includes("\\") ||
    normalizedFolder === "." ||
    normalizedFolder === ".." ||
    normalizedFolder.startsWith(".")
  ) {
    throw new Error("项目目录只能是单层目录名，不能包含路径分隔符或以点开头。");
  }

  const projectType = await quickAddApi.suggester(
    ["因子研究", "策略回测", "机器学习", "数据研究", "其他"],
    ["因子研究", "策略回测", "机器学习", "数据研究", "其他"]
  );
  if (!projectType) {
    params.abort?.("已取消创建项目");
    return;
  }

  const projectStatus = await quickAddApi.suggester(
    ["规划中", "进行中", "暂停"],
    ["规划中", "进行中", "暂停"]
  );
  if (!projectStatus) {
    params.abort?.("已取消创建项目");
    return;
  }

  const currentStage = await quickAddApi.suggester(
    ["研究设计", "数据处理", "因子测试", "模型训练", "回测验证", "报告整理"],
    ["研究设计", "数据处理", "因子测试", "模型训练", "回测验证", "报告整理"]
  );
  if (!currentStage) {
    params.abort?.("已取消创建项目");
    return;
  }

  const frequency = await quickAddApi.suggester(
    ["高频", "日频", "周频", "月频", "其他"],
    ["高频", "日频", "周频", "月频", "其他"]
  );
  if (!frequency) {
    params.abort?.("已取消创建项目");
    return;
  }

  const method = await quickAddApi.suggester(
    ["因子构建", "机器学习", "LightGBM", "组合优化", "回测", "其他"],
    ["因子构建", "机器学习", "LightGBM", "组合优化", "回测", "其他"]
  );
  if (!method) {
    params.abort?.("已取消创建项目");
    return;
  }

  const sourceRoot = "03_Templates/Project_Template";
  const targetRoot = `01_Projects/${normalizedFolder}`;
  const statusTemplatePath = "03_Templates/Project_Create_Template.md";

  if (await adapter.exists(targetRoot)) {
    throw new Error(`目标目录已存在：${targetRoot}`);
  }
  if (!(await adapter.exists(sourceRoot))) {
    throw new Error(`找不到项目模板：${sourceRoot}`);
  }
  if (!(await adapter.exists(statusTemplatePath))) {
    throw new Error(`找不到项目状态模板：${statusTemplatePath}`);
  }

  await copyFolder(adapter, sourceRoot, targetRoot);

  const statusTemplate = await adapter.read(statusTemplatePath);
  const now = new Date();
  const today = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
  const renderedStatus = statusTemplate
    .replaceAll("{{VALUE:project_status}}", escapeYamlDoubleQuoted(projectStatus))
    .replaceAll("{{VALUE:current_stage}}", escapeYamlDoubleQuoted(currentStage))
    .replaceAll("{{VALUE:project_type}}", escapeYamlDoubleQuoted(projectType))
    .replaceAll("{{VALUE:frequency}}", escapeYamlDoubleQuoted(frequency))
    .replaceAll("{{VALUE:method}}", escapeYamlDoubleQuoted(method))
    .replaceAll("{{DATE:YYYY-MM-DD}}", today);

  await adapter.write(`${targetRoot}/PROJECT_STATUS.md`, renderedStatus);

  variables.project_folder = normalizedFolder;
  variables.project_status = projectStatus;
  variables.current_stage = currentStage;
  variables.project_type = projectType;
  variables.frequency = frequency;
  variables.method = method;

  const readme = app.vault.getAbstractFileByPath(`${targetRoot}/README.md`);
  if (readme) {
    await app.workspace.getLeaf(true).openFile(readme);
  }

  return targetRoot;
};

async function copyFolder(adapter, sourceFolder, targetFolder) {
  await adapter.mkdir(targetFolder);
  const listing = await adapter.list(sourceFolder);

  for (const sourceSubfolder of listing.folders) {
    const relativePath = sourceSubfolder.slice(sourceFolder.length);
    await copyFolder(adapter, sourceSubfolder, `${targetFolder}${relativePath}`);
  }

  for (const sourceFile of listing.files) {
    const relativePath = sourceFile.slice(sourceFolder.length);
    const content = await adapter.readBinary(sourceFile);
    await adapter.writeBinary(`${targetFolder}${relativePath}`, content);
  }
}

function escapeYamlDoubleQuoted(value) {
  return String(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"');
}
