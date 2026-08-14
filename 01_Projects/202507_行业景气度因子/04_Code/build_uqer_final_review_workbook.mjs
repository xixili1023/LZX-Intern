import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const root = "/Users/lizhexi/Desktop/LZX-Intern";
const dataDir = `${root}/01_Projects/202507_行业景气度因子/04_Code/data`;
const bundlePath = `${dataDir}/uqer_final_review_bundle_20260811.json`;
const prosperityPath = `${dataDir}/uqer_industry_prosperity_list_20260812.csv`;
const outputPath = `${root}/UQER行业景气指标清单_28行业各30条_20260812.xlsx`;
const previewDir = `${root}/outputs/019fda3f-1632-7141-a309-3c2929dadb57`;

const bundle = JSON.parse(await fs.readFile(bundlePath, "utf8"));

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  const source = text.replace(/^\uFEFF/, "");
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (quoted) {
      if (char === '"' && source[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  const [headers, ...data] = rows;
  return data.filter((values) => values.some((value) => value !== "")).map((values) =>
    Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])),
  );
}

const prosperityRows = parseCsv(await fs.readFile(prosperityPath, "utf8"));
const industryCounts = new Map();
for (const row of prosperityRows) {
  industryCounts.set(row.industry_code, (industryCounts.get(row.industry_code) ?? 0) + 1);
}
const approvedIds = new Set(bundle.reviewed.map((row) => String(row.uqer_indic_id)));
const approvedOverlap = prosperityRows.filter((row) => approvedIds.has(String(row.uqer_indic_id)));
if (
  prosperityRows.length !== 840
  || industryCounts.size !== 28
  || [...industryCounts.values()].some((count) => count !== 30)
  || approvedOverlap.length
) {
  throw new Error(JSON.stringify({
    message: "行业景气指标清单未通过结构校验",
    rows: prosperityRows.length,
    industries: industryCounts.size,
    perIndustry: [...industryCounts.entries()],
    approvedOverlap: approvedOverlap.map((row) => row.uqer_indic_id),
  }));
}
const workbook = Workbook.create();
const colorNames = { yellow: "黄色", green: "绿色", blue: "蓝色" };
const approvalFills = { yellow: "#FFFF00", green: "#92D050", blue: "#00B0F0" };
const headerFormat = {
  fill: "#1F4E78",
  font: { name: "Microsoft YaHei", size: 10, bold: true, color: "#FFFFFF" },
  verticalAlignment: "center",
  horizontalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
};
const titleFormat = {
  fill: "#17365D",
  font: { name: "Microsoft YaHei", size: 16, bold: true, color: "#FFFFFF" },
  verticalAlignment: "center",
};
const bodyFont = { name: "Microsoft YaHei", size: 10, color: "#000000" };

function clean(value) {
  return value === null || value === undefined || String(value) === "nan" ? "" : value;
}

function colLetter(index) {
  let number = index + 1;
  let result = "";
  while (number > 0) {
    const remainder = (number - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    number = Math.floor((number - 1) / 26);
  }
  return result;
}

function writeMatrix(sheet, startRow, startCol, matrix) {
  if (!matrix.length || !matrix[0].length) return;
  sheet.getRangeByIndexes(startRow, startCol, matrix.length, matrix[0].length).values = matrix;
}

function styleDataSheet(sheet, rows, cols, widths, wrapColumns) {
  const lastCol = colLetter(cols - 1);
  const used = sheet.getRange(`A1:${lastCol}${rows}`);
  used.format.font = bodyFont;
  used.format.verticalAlignment = "center";
  sheet.getRange(`A1:${lastCol}1`).format = headerFormat;
  sheet.getRange(`A1:${lastCol}1`).format.rowHeight = 42;
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = true;
  for (let col = 0; col < cols; col += 1) {
    sheet.getRangeByIndexes(0, col, rows, 1).format.columnWidth = widths[col] ?? 14;
  }
  for (const col of wrapColumns) {
    sheet.getRange(`${col}2:${col}${rows}`).format.wrapText = true;
  }
  if (rows > 1) sheet.getRange(`A2:${lastCol}${rows}`).format.rowHeight = 48;
}

// 使用说明
{
  const sheet = workbook.worksheets.add("使用说明");
  sheet.getRange("A1:H1").merge();
  sheet.getRange("A1").values = [["UQER 行业指标复核与行业景气指标清单"]];
  sheet.getRange("A1:H1").format = titleFormat;
  sheet.getRange("A1:H1").format.rowHeight = 34;
  const rows = [
    ["项目", "说明", "本次处理", "后续动作", "", "", "", ""],
    ["黄色", "用户认为可直接替代", "仍复核地区、统计对象、产品规格和口径；发现冲突会下调", "查看“审批指标复核”的复核结论", "", "", "", ""],
    ["绿色", "用户不确定", "逐条深审", "优先查看“待重点确认”", "", "", "", ""],
    ["蓝色", "允许纳入但不是原始指标", "统一作为补充指标", "不替换原序列", "", "", "", ""],
    ["优先规则", "同一 mapping_row_id × UQER ID 两表颜色冲突", "以优先审核表为准", "已执行", "", "", "", ""],
    ["景气清单", "28 个申万一级行业，每个行业 30 条", "共 840 条行业—指标映射", "在“行业景气指标清单”中审批", "", "", "", ""],
    ["频率规则", "在统计对象、地区与口径正确的前提下，日频优先", "同时保留必要的周、旬、月、季频指标", "不得用高频错误指标替代低频正确指标", "", "", "", ""],
    ["地区规则", "全国/全球目标", "不允许被单一省市、企业或国外地区静默替代", "地区代理必须明确标注", "", "", "", ""],
    ["化工/有色", "核对中文、英文、规格、牌号、纯度、HS 编码", "已对 PTA、纯 MDI、钛白粉、维生素E、铜/铝等重点复核", "仍需数值和来源口径对账", "", "", "", ""],
    ["更新时间", "isUpdate=1 不代表日频；updateTime 也不等于首次发布日期", "频率以 frequency 字段为准", "正式回测必须检查观测级 publishDate", "", "", "", ""],
    ["结论边界", "“可直接替代”是元数据层结论", "尚未证明历史数值逐点一致", "下载通过项后做数值、发布时间和因子稳定性对账", "", "", "", ""],
    ["多行业映射", "同一 UQER 指标可以对应两个或三个行业", "保留行业映射行，不按指标 ID 强制去重", "行业用途分别审批", "", "", "", ""],
    ["审批方式", "新清单没有黄色、绿色或蓝色高亮", "请直接在“用户审批”列选择", "也可以自行高亮并写备注", "", "", "", ""],
  ];
  writeMatrix(sheet, 2, 0, rows);
  sheet.getRange("A3:D3").format = headerFormat;
  sheet.getRange(`A4:D${rows.length + 2}`).format.font = bodyFont;
  sheet.getRange(`A4:D${rows.length + 2}`).format.wrapText = true;
  sheet.getRange(`A4:D${rows.length + 2}`).format.verticalAlignment = "center";
  sheet.getRange(`A4:D${rows.length + 2}`).format.rowHeight = 46;
  sheet.getRange("A4").format.fill = approvalFills.yellow;
  sheet.getRange("A5").format.fill = approvalFills.green;
  sheet.getRange("A6").format.fill = approvalFills.blue;
  [14, 34, 44, 42, 4, 4, 4, 4].forEach((width, i) => {
    sheet.getRangeByIndexes(0, i, rows.length + 2, 1).format.columnWidth = width;
  });
  sheet.freezePanes.freezeRows(3);
  sheet.showGridLines = false;
}

// 审批指标复核
const reviewHeaders = [
  "原审批颜色", "复核结论", "复核优先级", "行业代码", "原指标名称", "Wind代码", "指标职能", "计算口径",
  "UQER指标名称", "UQER ID", "英文名称", "频率", "单位", "统计类型", "地区", "国家", "来源", "起始日期",
  "截止日期", "持续更新", "地区核对", "术语核对", "产品/口径核对", "复核理由", "主要风险", "建议动作",
  "时点提示", "UQER API", "mapping_row_id", "审批来源",
];
const reviewRows = bundle.reviewed.map((row) => [
  colorNames[row.approval_color], clean(row.review_status), clean(row.review_priority), clean(row.industry_code),
  clean(row.wind_name), clean(row.wind_code), clean(row.function_type), clean(row.calculation_type), clean(row.uqer_name),
  clean(row.uqer_indic_id), clean(row.meta_name_en), clean(row.uqer_frequency), clean(row.uqer_unit), clean(row.uqer_stat_type),
  clean(row.uqer_region), clean(row.meta_country), clean(row.uqer_source), clean(row.uqer_begin_date), clean(row.uqer_end_date),
  clean(row.uqer_is_update), clean(row.scope_check), clean(row.term_check), clean(row.product_check), clean(row.review_reason),
  clean(row.risk_flags), clean(row.recommended_action), clean(row.point_in_time_note), clean(row.uqer_api),
  clean(row.mapping_row_id), row.approval_source === "priority" ? "优先审核表" : "完整候选表",
]);
{
  const sheet = workbook.worksheets.add("审批指标复核");
  writeMatrix(sheet, 0, 0, [reviewHeaders, ...reviewRows]);
  styleDataSheet(
    sheet,
    reviewRows.length + 1,
    reviewHeaders.length,
    [9, 12, 9, 10, 42, 14, 11, 10, 42, 14, 42, 7, 12, 12, 14, 10, 22, 12, 12, 9, 24, 42, 36, 50, 38, 32, 40, 24, 11, 12],
    ["E", "I", "K", "U", "V", "W", "X", "Y", "Z", "AA"],
  );
  const table = sheet.tables.add(`A1:AD${reviewRows.length + 1}`, true, "ApprovalReviewTable");
  table.style = "TableStyleLight1";
  table.showFilterButton = true;
  bundle.reviewed.forEach((row, index) => {
    const excelRow = index + 2;
    sheet.getRange(`A${excelRow}:AD${excelRow}`).format.fill = approvalFills[row.approval_color];
    if (row.review_status === "不可替代") {
      sheet.getRange(`B${excelRow}`).format.font = { name: "Microsoft YaHei", size: 10, bold: true, color: "#C00000" };
    } else if (row.review_status === "可直接替代") {
      sheet.getRange(`B${excelRow}`).format.font = { name: "Microsoft YaHei", size: 10, bold: true, color: "#006100" };
    }
  });
}

// 行业景气指标清单：只保留用户当前审批所需的基础字段。
const listHeaders = [
  "行业代码", "行业名称", "行业内序号", "UQER指标ID", "UQER中文名", "UQER英文名", "频率", "单位",
  "统计类型", "地区", "国家", "数据来源", "UQER API", "历史开始", "历史结束", "更新状态", "用户审批", "用户备注",
];
const listRows = prosperityRows.map((row) => [
  clean(row.industry_code), clean(row.industry_name), Number(row.industry_rank), clean(row.uqer_indic_id),
  clean(row.uqer_name), clean(row.name_en), clean(row.frequency), clean(row.unit), clean(row.stat_type), clean(row.region),
  clean(row.country), clean(row.source), clean(row.api), clean(row.begin_date), clean(row.end_date),
  String(row.is_update) === "1" ? "持续更新" : "停止更新", "", "",
]);
{
  const sheet = workbook.worksheets.add("行业景气指标清单");
  writeMatrix(sheet, 0, 0, [listHeaders, ...listRows]);
  styleDataSheet(
    sheet,
    listRows.length + 1,
    listHeaders.length,
    [10, 12, 9, 14, 44, 44, 7, 12, 12, 14, 10, 24, 24, 12, 12, 10, 12, 34],
    ["E", "F", "L", "M", "R"],
  );
  const table = sheet.tables.add(`A1:R${listRows.length + 1}`, true, "ProsperityIndicatorTable");
  table.style = "TableStyleLight1";
  table.showBandedRows = false;
  table.showFilterButton = true;
  sheet.getRange(`A2:R${listRows.length + 1}`).format.fill = "#FFFFFF";
  sheet.getRange(`Q2:Q${listRows.length + 1}`).dataValidation = {
    rule: { type: "list", values: ["通过", "保留观察", "不采用"] },
  };
}

// 复核汇总（公式驱动）
{
  const sheet = workbook.worksheets.add("复核汇总");
  sheet.getRange("A1:H1").merge();
  sheet.getRange("A1").values = [["复核结果汇总"]];
  sheet.getRange("A1:H1").format = titleFormat;
  sheet.getRange("A3:B3").values = [["审批复核指标", "数量"]];
  sheet.getRange("A4:A11").values = [["总数"], ["黄色"], ["绿色"], ["蓝色"], ["可直接替代"], ["近似替代"], ["仅补充"], ["不可替代"]];
  const reviewEnd = reviewRows.length + 1;
  sheet.getRange("B4:B11").formulas = [
    [`=COUNTA('审批指标复核'!A2:A${reviewEnd})`],
    [`=COUNTIF('审批指标复核'!A2:A${reviewEnd},"黄色")`],
    [`=COUNTIF('审批指标复核'!A2:A${reviewEnd},"绿色")`],
    [`=COUNTIF('审批指标复核'!A2:A${reviewEnd},"蓝色")`],
    [`=COUNTIF('审批指标复核'!B2:B${reviewEnd},"可直接替代")`],
    [`=COUNTIF('审批指标复核'!B2:B${reviewEnd},"近似替代")`],
    [`=COUNTIF('审批指标复核'!B2:B${reviewEnd},"仅补充")`],
    [`=COUNTIF('审批指标复核'!B2:B${reviewEnd},"不可替代")`],
  ];
  sheet.getRange("D3:H3").values = [["原审批颜色", "可直接替代", "近似替代", "仅补充", "不可替代"]];
  sheet.getRange("D4:D6").values = [["黄色"], ["绿色"], ["蓝色"]];
  for (let r = 4; r <= 6; r += 1) {
    for (let c = 5; c <= 8; c += 1) {
      const colorCell = `D${r}`;
      const statusCell = `${colLetter(c - 1)}3`;
      sheet.getRangeByIndexes(r - 1, c - 1, 1, 1).formulas = [[
        `=COUNTIFS('审批指标复核'!A2:A${reviewEnd},${colorCell},'审批指标复核'!B2:B${reviewEnd},${statusCell})`,
      ]];
    }
  }
  sheet.getRange("A14:B14").values = [["行业景气指标清单", "数量"]];
  sheet.getRange("A15:A23").values = [["总映射数"], ["覆盖行业"], ["每行业最少"], ["每行业最多"], ["日频"], ["周频"], ["旬频"], ["月频"], ["季频"]];
  const listEnd = listRows.length + 1;
  sheet.getRange("B15:B23").formulas = [
    [`=COUNTA('行业景气指标清单'!A2:A${listEnd})`],
    ["=28"],
    ["=30"],
    ["=30"],
    [`=COUNTIF('行业景气指标清单'!G2:G${listEnd},"日")`],
    [`=COUNTIF('行业景气指标清单'!G2:G${listEnd},"周")`],
    [`=COUNTIF('行业景气指标清单'!G2:G${listEnd},"旬")`],
    [`=COUNTIF('行业景气指标清单'!G2:G${listEnd},"月")`],
    [`=COUNTIF('行业景气指标清单'!G2:G${listEnd},"季")`],
  ];
  sheet.getRange("D14:H14").merge();
  sheet.getRange("D14").values = [["关键结论"]];
  sheet.getRange("D15:H22").merge(true);
  sheet.getRange("D15:D22").values = [
    ["黄色并非全部可直接替代：产品子项、统计变化率和价格水平混用时已下调。"],
    ["绿色只有 1 条通过为可直接替代；其余需要近似、补充或剔除处理。"],
    ["全国目标优先使用全国/全市场指标；地区或公司数据只作为明确代理。"],
    ["景气清单共 840 条，覆盖 28 个申万一级行业，每个行业严格 30 条。"],
    ["清单已排除前序审批指标；同一指标可合理映射多个行业。"],
    ["清单页无审批高亮；日频优先，但没有为了日频牺牲统计对象正确性。"],
    ["本轮只维护指标清单；公式、方向、滞后与因子检验暂不展开。"],
    ["所有指标进入正式回测前仍需检查观测级发布时间和历史数值。"],
  ];
  sheet.getRange("A3:B3").format = headerFormat;
  sheet.getRange("D3:H3").format = headerFormat;
  sheet.getRange("A14:B14").format = headerFormat;
  sheet.getRange("D14:H14").format = headerFormat;
  sheet.getRange("A4:B23").format.font = bodyFont;
  sheet.getRange("D4:H6").format.font = bodyFont;
  sheet.getRange("D15:H22").format.font = bodyFont;
  sheet.getRange("D15:H22").format.wrapText = true;
  sheet.getRange("D15:H22").format.rowHeight = 40;
  sheet.getRange("A4").format.font = { name: "Microsoft YaHei", size: 10, bold: true };
  sheet.getRange("D4").format.fill = approvalFills.yellow;
  sheet.getRange("D5").format.fill = approvalFills.green;
  sheet.getRange("D6").format.fill = approvalFills.blue;
  [26, 12, 4, 18, 16, 16, 14, 14].forEach((width, i) => {
    sheet.getRangeByIndexes(0, i, 23, 1).format.columnWidth = width;
  });
  sheet.freezePanes.freezeRows(3);
  sheet.showGridLines = false;
}

// 待重点确认
{
  const focusHeaders = ["来源", "原审批颜色", "行业", "原目标/关联目标", "UQER指标", "当前结论", "重点原因", "建议动作", "引用ID"];
  const approvalFocus = bundle.reviewed
    .filter((row) => row.review_priority === "高")
    .map((row) => [
      "审批复核", colorNames[row.approval_color], clean(row.industry_code), clean(row.wind_name), clean(row.uqer_name),
      clean(row.review_status), `${clean(row.review_reason)}；${clean(row.risk_flags)}`, clean(row.recommended_action),
      `${clean(row.mapping_row_id)} / ${clean(row.uqer_indic_id)}`,
    ]);
  const rows = approvalFocus;
  const sheet = workbook.worksheets.add("待重点确认");
  writeMatrix(sheet, 0, 0, [focusHeaders, ...rows]);
  styleDataSheet(sheet, rows.length + 1, focusHeaders.length, [12, 11, 16, 42, 44, 15, 60, 38, 18], ["D", "E", "G", "H"]);
  const table = sheet.tables.add(`A1:I${rows.length + 1}`, true, "FocusReviewTable");
  table.style = "TableStyleLight1";
  table.showFilterButton = true;
  bundle.reviewed.filter((row) => row.review_priority === "高").forEach((row, index) => {
    sheet.getRange(`A${index + 2}:I${index + 2}`).format.fill = approvalFills[row.approval_color];
  });
}

await fs.mkdir(previewDir, { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

const summaryPreview = await workbook.render({ sheetName: "复核汇总", range: "A1:H23", scale: 1, format: "png" });
await fs.writeFile(`${previewDir}/UQER行业指标复核与新增候选_20260811-preview.png`, new Uint8Array(await summaryPreview.arrayBuffer()));
const reviewPreview = await workbook.render({ sheetName: "审批指标复核", range: "A1:L12", scale: 1, format: "png" });
await fs.writeFile(`${previewDir}/UQER审批复核-preview.png`, new Uint8Array(await reviewPreview.arrayBuffer()));
const listPreview = await workbook.render({ sheetName: "行业景气指标清单", range: "A1:R12", scale: 1, format: "png" });
await fs.writeFile(`${previewDir}/UQER行业景气指标清单-preview.png`, new Uint8Array(await listPreview.arrayBuffer()));

const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 7000,
  tableMaxRows: 4,
  tableMaxCols: 10,
  tableMaxCellChars: 100,
});
console.log(overview.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
});
console.log(errors.ndjson);
console.log(JSON.stringify({ outputPath, reviewed: reviewRows.length, prosperityMappings: listRows.length, industries: industryCounts.size }));
