# 行业景气数据代码

本目录把数据获取与数据转换分成两个独立阶段：

- `download_uqer_industry_indicators.py`：从 UQER/通联网关下载原始元数据与观测值，不构造因子。
- `uqer_industry_api_catalog.csv`：记录接口、研究类别、抽样指标和待核对项；新增接口优先改清单，不复制脚本。
- `uqer_indicator_selection_template.csv`：已审核指标下载清单模板；`selected` 模式只下载表中启用的代码。
- `uqer_wind_crosswalk_template.csv`：Wind–UQER 人工映射表字段模板；元数据下载后再填充。
- `profile_uqer_industry_snapshot.py`：为一个原始快照生成 API 覆盖、指标概览、最新样本和质量报告。
- `process_industry_indicators.py`：处理原实习 Wind EDB 宽表；后续应扩展或新增 UQER 标准化程序，但不要覆盖原始快照。

## 为什么不是一个指标一个文件

所有 `EcoData*Get` 接口都返回同一组核心字段，因此使用一个配置驱动的下载器。数据按 `API × 请求批次` 分区，而不是每条指标单独保存：

- 避免数百个重复脚本和小文件；
- 某个接口或批次失败时可以精确定位；
- 同一批指标共享请求，减少调用次数与流量；
- manifest 记录参数、行数、日期范围和文件哈希，便于复现。

默认保存位置：

```text
~/Desktop/InternData/行业景气度项目Data/raw/uqer_industry_indicators/
└── snapshot=YYYYMMDDTHHMMSSZ/
    ├── metadata/<api>.parquet
    ├── data/api=<api>/part-0001.parquet
    └── manifest.json
```

## 下载模式

- `sample`：每个接口只请求清单中的示例指标，用于连通性和字段检查。
- `metadata`：只盘点指定 API 的元数据，不请求历史观测。
- `selected`：只下载人工审核清单中的指标，是正式取数的默认方式。
- `full`：下载 API 下发现的所有指标；必须显式使用 `--allow-all-indicators`，不建议用于常规研究。

数值接口与元数据字段使用不同命名：例如数值请求是 `EcoDataIndChemicalGet`，`EcoInfoProGet.dataApiName` 中则是 `getEcoDataIndChemical`。两者都在接口清单中显式记录，不在代码中猜测转换。

## 推荐运行顺序

先确认本机已连接公司网关所需网络，并设置管理员提供的环境变量。不要把地址、密钥或 token 写进仓库。

先抽样：

```bash
python 01_Projects/202507_行业景气度因子/04_Code/data/download_uqer_industry_indicators.py \
  sample --start-date 20240101 --end-date 20241231
```

抽样后生成质量报告：

```bash
python 01_Projects/202507_行业景气度因子/04_Code/data/download_uqer_industry_indicators.py \
  sample --start-date 20240101 --snapshot-id sample-YYYYMMDD-v1

python 01_Projects/202507_行业景气度因子/04_Code/data/profile_uqer_industry_snapshot.py \
  ~/Desktop/InternData/行业景气度项目Data/raw/uqer_industry_indicators/snapshot=sample-YYYYMMDD-v1 \
  --output-dir ~/Desktop/InternData/行业景气度项目Data/processed/uqer_industry_indicators/sample-YYYYMMDD-v1
```

然后只对需要的 API 执行元数据盘点，建立 Wind–UQER 映射。映射审核后，把已选指标写入 selection CSV 并下载历史值：

```bash
python 01_Projects/202507_行业景气度因子/04_Code/data/download_uqer_industry_indicators.py \
  selected --start-date 20150101 \
  --selection path/to/uqer_indicator_selection.csv
```

只验证某一个接口：

```bash
python 01_Projects/202507_行业景气度因子/04_Code/data/download_uqer_industry_indicators.py \
  sample --start-date 20240101 --end-date 20241231 \
  --apis EcoDataIndAgriculturalGet
```

## 2026-08-07 真实抽样结果

- 有效快照：`sample-20260807-v2`，覆盖 `2024-01-01` 至 `2026-08-07`。
- 24 个启用 API 共完成 48 次请求，零失败；返回 26 行元数据和 2,786 行观测。
- 24 个唯一样本指标中，17 个在抽样区间有数值；7 个示例指标因早已停更而无数据。
- 760 行观测（约 27.28%）缺失 `publishDate`；这些行不能直接进入无前视回测。
- 化工和机械设备的样本元数据各有 1 条完全重复，标准化时必须按指标主键去重并保留原始快照。
- 化工 API 仅元数据就约有 93,979 行，证明必须先做指标映射，再用 `selected` 模式下载。

详细解读见 [[../../01_Research/UQER行业指标真实抽样检查|UQER 行业指标真实抽样检查]]。

## 当前必须人工核对的项目

用户提供的接口列表有三组完全重复且名称不一致的映射，清单已默认停用可疑行：

1. 信息服务与轻工制造都指向 `EcoDataIndLightmanufactueGet / 2130000009`；
2. 有色金属与综合都指向 `EcoDataIndOthersGet / 2220000007`；
3. 公用事业与行业财务都指向 `EcoDataFinGet / 2020500033`。

2026-08-07 实测中，`EcoDataFinGet / 2020500033` 的元数据和观测值均为空，因此两行都已默认停用，直到找到正确的 API 或指标代码。

在 UQER 页面核实正确 API/指标代码后，修改清单并启用，不要在代码里静默猜测。

完整对账方法见 [[../../01_Research/UQER与Wind景气指标对账方案|UQER 与 Wind 景气指标对账方案]]。
