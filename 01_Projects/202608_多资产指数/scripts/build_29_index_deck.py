"""重构29只券商多资产指数的答辩数据、图片与Markdown。"""

from __future__ import annotations

import math
import re
from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from metrics import clean_prices, performance_metrics, split_at_publication


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CUTOFF = pd.Timestamp("2026-08-05")
RISK_FREE_RATE = 0.015
RAW_FILE = DATA_DIR / "29只券商多资产配置指数_原始数据.xlsx"
GT01_SUPPLEMENT_FILE = DATA_DIR / "GT01.WI_国泰全天候低波_日行情.xlsx"
RESULTS = ROOT / "results"
REPORT_DIR = ROOT / "reports"
FIGURES = REPORT_DIR / "figures"
REPORT = REPORT_DIR / "券商多资产配置指数_重构版.md"
LEGACY_FIGURES_DIR = ROOT / "figures" / "答辩重构"
PINGFANG_COLLECTION = Path(
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/"
    "86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc"
)
PINGFANG_SC_REGULAR = ROOT / ".matplotlib" / "fonts" / "PingFangSC-Regular.ttf"

CHART_STYLE = {
    "figure_facecolor": "#FFFFFF",
    "axes_facecolor": "#FAFAFA",
    "text": "#26333D",
    "muted_text": "#6F7880",
    "grid": "#D8DEE3",
    "spine": "#BCC4CA",
}

RESEARCH_COLORS = {
    "primary": "#355F78",
    "secondary": "#5D7F89",
    "teal": "#587E78",
    "negative": "#A85B63",
    "up": "#A85B63",
    "down": "#587E78",
    "better": "#A85B63",
    "worse": "#587E78",
    "purple": "#706A8A",
    "neutral": "#9AA2A8",
    "light_neutral": "#BCC4CA",
    "accent": "#9B7A45",
}

FOCUS_CODES = ["CI011800.WI", "CICSF040.WI", "CI011001.WI", "GALLW.WI"]
FOCUS_COLORS = {
    "CI011800.WI": RESEARCH_COLORS["primary"],
    "CICSF040.WI": RESEARCH_COLORS["secondary"],
    "CI011001.WI": RESEARCH_COLORS["accent"],
    "GALLW.WI": RESEARCH_COLORS["purple"],
}

# 公众号的22只有效样本按原文顺序录入；余下7只为停更/数据不足组。
ARTICLE_ORDER = [
    "CI011001.WI", "GMARS.WI", "CI011800.WI", "CMARS2.WI", "CICSF040.WI",
    "GALLW.WI", "GSAW.WI", "CALLW.WI", "SWALLW.WI", "801639.SI",
    "HAWS1.WI", "CARP2.WI", "GT01.WI", "CI066001.WI", "GCA.WI",
    "GCAPLUS.WI", "GMATPLUS.WI", "CMAT.WI", "QMATS.WI", "HYCLES1X.WI",
    "SWSMART2.WI", "VENUS.WI", "GARP.WI", "CI017003.WI", "CMAM.WI",
    "CALLWE.WI", "GLMS888806.WI", "SMILE1.WI", "GMATMAX.WI",
]
ARTICLE_PUBLIC_RECORD = {"CICSF040.WI", "SWSMART2.WI", "VENUS.WI"}
ARTICLE_SPECIAL = set(ARTICLE_ORDER[22:])
ARTICLE_COMPARABLE = set(ARTICLE_ORDER[:22]).difference(ARTICLE_PUBLIC_RECORD)

ARTICLE_JUDGEMENT = {
    "CI011001.WI": "样本外更好", "GMARS.WI": "严重过拟合",
    "CI011800.WI": "样本外更好", "CMARS2.WI": "基本一致",
    "CICSF040.WI": "暂不判断", "GALLW.WI": "过拟合",
    "GSAW.WI": "严重过拟合", "CALLW.WI": "基本一致",
    "SWALLW.WI": "基本一致", "801639.SI": "过拟合",
    "HAWS1.WI": "严重过拟合", "CARP2.WI": "基本一致",
    "GT01.WI": "基本一致", "CI066001.WI": "基本一致",
    "GCA.WI": "过拟合", "GCAPLUS.WI": "过拟合",
    "GMATPLUS.WI": "过拟合", "CMAT.WI": "基本一致",
    "QMATS.WI": "严重过拟合", "HYCLES1X.WI": "严重过拟合",
    "SWSMART2.WI": "暂不判断", "VENUS.WI": "暂不判断",
}

# 用于图06的原文数字；只对四只重点指数做可核对的逐项录入。
ARTICLE_FOCUS = {
    ("CI011800.WI", "pre"): (0.0336, -0.0993, np.nan, 0.25),
    ("CI011800.WI", "post"): (0.1932, -0.1029, np.nan, 1.58),
    ("CICSF040.WI", "all"): (0.1141, -0.0385, 0.0469, 2.08),
    ("CI011001.WI", "pre"): (0.0680, -0.0462, 0.0380, 1.56),
    ("CI011001.WI", "post"): (0.0949, -0.0304, 0.0394, 1.95),
    ("GALLW.WI", "pre"): (0.1238, -0.0544, 0.0604, 3.90),
    ("GALLW.WI", "post"): (0.0864, -0.0799, 0.1000, 1.61),
}

ARTICLE_SHARPE_FREQUENCY = {
    ("CICSF040.WI", "all"): "月频",
}

ARTICLE_CASE_EVALUATIONS = {
    "CI011800.WI": (
        "原文将其视为29只中发布后表现最好的“明星”，同时提醒发布前仅约0.86年，"
        "2025年高收益可能集中于特定资产或市场环境，可持续性仍需检验。"
    ),
    "CICSF040.WI": (
        "原文将其视为长期运行的稳健样本，强调基日等于发布日期、长期收益较高且回撤较低；"
        "但其关于月频年化夏普再“换算为日频”的说法需要修正。"
    ),
    "CI011001.WI": (
        "原文将其视为少数发布后表现更好的指数，并将部分优势解释为2019—2021年市场环境贡献，"
        "认为策略逻辑可能有效但也享受了环境红利。"
    ),
    "GALLW.WI": (
        "原文把发布前夏普3.90视为“完美曲线”，指出发布后夏普回落但仍为正，"
        "同时强调发布后仅约0.7年，需要继续观察。"
    ),
}

CASE_SOURCE_NOTES = {
    "CI011800.WI": "未找到发行同期官方方法书；当前资产范围主要依据Wind历史成分记录。",
    "CICSF040.WI": (
        "[中信期货官方披露](https://www.citicsf.com/e-futures/about/disclosure?id=734599)"
        "确认宏观因子配置叠加风险平价框架，但不足以证明2015年发行时规则完全相同。"
    ),
    "CI011001.WI": "当前可得材料主要为发布后的配置框架研究，不能倒推为2019年发行时完整规则。",
    "GALLW.WI": (
        "[银河证券2025年报](https://cdn.chinastock.com.cn/omc/investRelation/sh/601881_20260331_XWZA.pdf)"
        "只确认落地全天候大类资产配置指数，未披露资产池和权重机制。"
    ),
}

FIGURE_NAMES = [
    "01_样本结构与复算范围.png",
    "02_收益与夏普联合变化.png",
    "03_收益衰减多维诊断.png",
    "04_原文值与统一复算.png",
    "05_四指数全历史走势.png",
    "06_CI011800走势.png",
    "07_CICSF040走势.png",
    "08_CI011001走势.png",
    "09_GALLW走势.png",
    "10_收益衰减敏感性.png",
]

LEGACY_FIGURE_NAMES = [
    "01_筛选方法与样本状态.png", "02_29只全景总览.png", "07_四指数横向比较.png",
    "06_公众号原文与复算.png",
    "01_样本数据状态.png", "02_全景判断分布.png", "03_发布前后收益比较.png",
    "04_发布前后夏普比较.png", "05_收益衰减排行.png", "06_重点指标原文值与复算.png",
    "07_四指数全历史走势.png", "08_CI011800走势.png", "09_CICSF040走势.png",
    "10_CI011001走势.png", "11_GALLW走势.png", "12_样本内表现与样本外衰减.png",
    "02_发布前后收益比较.png", "03_发布前后夏普比较.png", "04_收益衰减排行.png",
    "05_重点指标原文值与复算.png", "06_四指数全历史走势.png", "07_CI011800走势.png",
    "08_CICSF040走势.png", "09_CI011001走势.png", "10_GALLW走势.png",
    "11_样本内表现与样本外衰减.png",
    "08_CI011800个案页.png", "09_CICSF040个案页.png", "10_CI011001个案页.png",
    "11_GALLW个案页.png", "12_过拟合机制.png", "13_样本内表现与样本外衰减.png",
    "14_最终评价.png", "15_29只完整指标表_1.png", "16_29只完整指标表_2.png",
    "17_29只完整指标表_3.png",
]


def article_style_judgement(row: dict[str, object] | pd.Series) -> str:
    """按公众号以年化收益衰减2个百分点为界的简单逻辑分类。"""

    gap = pd.to_numeric(pd.Series([row.get("收益差")]), errors="coerce").iloc[0]
    if pd.isna(gap):
        return "暂不判断"
    if gap > 0.02:
        return "过拟合"
    if gap < -0.02:
        return "样本外更好"
    return "基本一致"


def project_comment(row: dict[str, object] | pd.Series) -> str:
    """生成一句话项目评价，并把样本与数据边界写进文字。"""

    status = str(row.get("数据状态", "") or "")
    judgement = str(row.get("复算判断", "暂不判断") or "暂不判断")
    post_years = pd.to_numeric(pd.Series([row.get("发布后年数")]), errors="coerce").iloc[0]
    if "无行情" in status or "未检索" in status:
        return "Wind未返回行情，保留样本占位，不做绩效判断。"
    if judgement == "暂不判断":
        text = "缺少可比的发布前回溯段，只报告公开序列表现。"
    elif judgement == "过拟合":
        text = "发布后年化收益明显衰减，与过拟合担忧一致，但不是因果证明。"
    elif judgement == "样本外更好":
        text = "发布后表现优于回溯段，不支持简单的“发布即失效”叙事。"
    else:
        text = "发布前后年化收益基本一致，未见明显收益衰减。"
    if pd.notna(post_years) and float(post_years) < 1:
        text += " 发布后不足1年，结论需继续观察。"
    if "停更" in status:
        text += " 序列已停更，结果截至最后有效日。"
    return text


def _find_column(columns: pd.Index, exact: tuple[str, ...], contains: tuple[str, ...] = ()) -> str | None:
    for name in exact:
        if name in columns:
            return name
    for name in columns:
        text = str(name)
        if all(piece in text for piece in contains):
            return str(name)
    return None


def merge_gt01_daily_rows(
    daily: pd.DataFrame,
    supplement: pd.DataFrame,
    extraction_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """用GT01单独导出的完整历史替换主表中的GT01不完整历史。"""

    target = daily.copy()
    code_column = _find_column(target.columns, ("Wind代码", "指数代码"), ("代码",))
    date_column = _find_column(target.columns, ("日期", "时间"), ("日期",))
    price_column = _find_column(target.columns, ("收盘价",), ("收盘价",))
    if not code_column or not date_column or not price_column:
        raise ValueError("Index_Daily缺少GT01合并所需的代码、日期或收盘价字段")

    source = supplement.copy()
    source_code = _find_column(source.columns, ("Wind代码", "指数代码"), ("代码",))
    source_name = _find_column(source.columns, ("证券简称", "指数简称"), ("简称",))
    source_date = _find_column(source.columns, ("日期", "时间"), ("日期",))
    source_price = _find_column(source.columns, ("收盘价",), ("收盘价",))
    source_currency = _find_column(source.columns, ("交易币种",), ("币种",))
    source_volume = _find_column(source.columns, ("成交量(股)",), ("成交量", "股"))
    required = {
        "代码": source_code,
        "日期": source_date,
        "收盘价": source_price,
    }
    missing = [label for label, column in required.items() if column is None]
    if missing:
        raise ValueError(f"GT01补充文件缺少必要字段：{','.join(missing)}")

    source = source.loc[source[source_code].astype(str) == "GT01.WI"].copy()
    source[source_date] = pd.to_datetime(source[source_date], errors="coerce").dt.normalize()
    source[source_price] = pd.to_numeric(source[source_price], errors="coerce")
    source = source.loc[source[source_date].notna() & source[source_price].notna()].copy()
    source = source.sort_values(source_date).drop_duplicates(source_date, keep="last")
    if source.empty:
        raise ValueError("GT01补充文件没有有效行情")

    rows = pd.DataFrame(index=source.index, columns=target.columns)
    rows[code_column] = "GT01.WI"
    if (name_column := _find_column(target.columns, ("证券简称", "指数简称"), ("简称",))):
        rows[name_column] = (
            source[source_name].astype(str).values
            if source_name
            else "国泰全天候低波"
        )
    rows[date_column] = source[source_date].values
    rows[price_column] = source[source_price].values
    if (currency_column := _find_column(target.columns, ("交易币种",), ("币种",))):
        rows[currency_column] = (
            source[source_currency].values if source_currency else "CNY"
        )
    if (earliest_column := _find_column(target.columns, ("最早交易日期",), ("最早交易", "日期"))):
        rows[earliest_column] = source[source_date].min()
    if (return_column := _find_column(target.columns, (), ("涨跌幅", "%"))):
        returns = source[source_price].pct_change(fill_method=None).mul(100).fillna(0.0)
        rows[return_column] = returns.values
    if (volume_column := _find_column(target.columns, ("成交量(股)",), ("成交量", "股"))):
        rows[volume_column] = source[source_volume].values if source_volume else np.nan
    if (last_valid_column := _find_column(target.columns, ("最后有效更新日期",), ("最后有效", "日期"))):
        rows[last_valid_column] = source[source_date].max()
    if (status_column := _find_column(target.columns, ("数据状态",), ("数据状态",))):
        rows[status_column] = "正常更新"
    if (extract_column := _find_column(target.columns, ("提取日期",), ("提取日期",))):
        rows[extract_column] = pd.Timestamp(
            extraction_date if extraction_date is not None else pd.Timestamp.today()
        ).normalize()
    if (source_column := _find_column(target.columns, ("数据来源",), ("数据来源",))):
        rows[source_column] = "Wind金融终端（GT01单独补充）"

    others = target.loc[target[code_column].astype(str) != "GT01.WI"].copy()
    return pd.concat([others, rows], ignore_index=True, sort=False)


def clean_index_daily(
    daily: pd.DataFrame,
    cutoff: pd.Timestamp = CUTOFF,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """清洗指数点位，并删除已标记停更序列尾部的前向填充值。"""

    frame = daily.copy()
    code_column = _find_column(frame.columns, ("Wind代码", "指数代码"), ("代码",))
    name_column = _find_column(frame.columns, ("证券简称", "指数简称"), ("简称",))
    date_column = _find_column(frame.columns, ("日期", "时间"), ("日期",))
    price_column = _find_column(frame.columns, ("收盘价",), ("收盘价",))
    status_column = _find_column(frame.columns, ("数据状态",), ("数据状态",))
    last_valid_column = _find_column(frame.columns, ("最后有效更新日期",), ("最后有效", "日期"))
    required = {"代码": code_column, "日期": date_column, "收盘价": price_column}
    missing = [label for label, column in required.items() if column is None]
    if missing:
        raise ValueError(f"Index_Daily缺少必要字段：{','.join(missing)}")

    rename = {code_column: "Wind代码", date_column: "日期", price_column: "收盘价"}
    if name_column:
        rename[name_column] = "证券简称"
    if status_column:
        rename[status_column] = "数据状态"
    if last_valid_column:
        rename[last_valid_column] = "最后有效更新日期"
    frame = frame.rename(columns=rename)
    if "证券简称" not in frame:
        frame["证券简称"] = ""
    if "数据状态" not in frame:
        frame["数据状态"] = ""
    if "最后有效更新日期" not in frame:
        frame["最后有效更新日期"] = pd.NaT

    frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce").dt.normalize()
    frame["收盘价"] = pd.to_numeric(frame["收盘价"], errors="coerce")
    frame["最后有效更新日期"] = pd.to_datetime(
        frame["最后有效更新日期"], errors="coerce"
    ).dt.normalize()
    frame = frame.loc[frame["日期"].notna() & frame["收盘价"].notna()].copy()
    frame = frame.loc[frame["日期"] <= pd.Timestamp(cutoff)].copy()
    frame = frame.sort_values(["Wind代码", "日期"]).drop_duplicates(
        ["Wind代码", "日期"], keep="last"
    )

    cleaned_groups: list[pd.DataFrame] = []
    audit_rows: list[dict[str, object]] = []
    for code, group in frame.groupby("Wind代码", sort=False):
        group = group.sort_values("日期").copy()
        original_count = len(group)
        status = "；".join(sorted({str(value) for value in group["数据状态"].dropna() if str(value)}))
        stop_date = pd.NaT
        if "停更后前向填充" in status and len(group) > 0:
            changed = group["收盘价"].ne(group["收盘价"].shift())
            change_dates = group.loc[changed, "日期"]
            derived_date = change_dates.max() if not change_dates.empty else pd.NaT
            explicit_dates = group["最后有效更新日期"].dropna()
            explicit_date = explicit_dates.max() if not explicit_dates.empty else pd.NaT
            candidates = [date for date in (derived_date, explicit_date) if pd.notna(date)]
            stop_date = max(candidates) if candidates else group["日期"].max()
            group = group.loc[group["日期"] <= stop_date].copy()
        cleaned_groups.append(group)
        audit_rows.append(
            {
                "Wind代码": code,
                "证券简称": group["证券简称"].iloc[0] if not group.empty else "",
                "清洗前有效行数": original_count,
                "清洗后有效行数": len(group),
                "删除的前向填充行数": original_count - len(group),
                "计算截止日": group["日期"].max() if not group.empty else pd.NaT,
                "数据状态": status or "正常更新",
            }
        )

    cleaned = pd.concat(cleaned_groups, ignore_index=True) if cleaned_groups else frame.iloc[0:0].copy()
    audit = pd.DataFrame(audit_rows)
    return cleaned, audit


def reconcile_article_universe(books: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """保留公众号29只样本，并为Wind未检索到的CALLWE补无行情占位。"""

    reconciled = {name: frame.copy() for name, frame in books.items()}
    info = reconciled["Index_Info"]
    source_codes = set(info["Wind代码"].dropna().astype(str))
    article_codes = set(ARTICLE_ORDER)
    unexpected = source_codes.difference(article_codes)
    missing = article_codes.difference(source_codes)
    if unexpected:
        raise ValueError(f"Index_Info包含公众号29只样本之外的代码：{sorted(unexpected)}")
    if missing.difference({"CALLWE.WI"}):
        raise ValueError(f"Index_Info缺少无法自动恢复的公众号样本：{sorted(missing)}")

    if "CALLWE.WI" in missing:
        info_placeholder = {
            "Wind代码": "CALLWE.WI",
            "证券简称": "高华中国全天候增强",
            "证券全称": "高华中国全天候增强（Wind未检索）",
            "发布日期": pd.Timestamp("2025-07-01"),
            "收益处理方式": "未说明",
            "数据状态": "停更/无数据",
            "数据来源": "公众号原文；Wind未检索",
        }
        reconciled["Index_Info"] = pd.concat(
            [info, pd.DataFrame([info_placeholder])], ignore_index=True, sort=False
        )

    selection = reconciled["Selection_Audit"]
    selection_codes = set(selection["Wind代码"].dropna().astype(str))
    if "CALLWE.WI" not in selection_codes:
        selection_placeholder = {
            "Wind代码": "CALLWE.WI",
            "证券简称": "高华中国全天候增强",
            "筛选关键词": "全天候",
            "真实资产类别": "待核验",
            "核验证据": "公众号原文；Wind未检索到该代码",
            "是否覆盖两个以上大类资产": "待核验",
            "纳入理由": "公众号29只样本",
            "异常状态": "停更/无数据",
        }
        reconciled["Selection_Audit"] = pd.concat(
            [selection, pd.DataFrame([selection_placeholder])], ignore_index=True, sort=False
        )

    daily = reconciled["Index_Daily"]
    if "Wind代码" in daily:
        callwe_rows = daily.loc[daily["Wind代码"].astype(str) == "CALLWE.WI"]
        if not callwe_rows.empty:
            price_column = _find_column(callwe_rows.columns, ("收盘价",), ("收盘价",))
            if price_column and pd.to_numeric(callwe_rows[price_column], errors="coerce").notna().any():
                raise ValueError("CALLWE.WI被写入了行情；不得复制CALLW.WI数据作为替代")

    final_codes = set(reconciled["Index_Info"]["Wind代码"].dropna().astype(str))
    if final_codes != article_codes:
        raise ValueError("对账后Index_Info未完整覆盖公众号29只样本")
    return reconciled


def load_source_workbook(path: Path = RAW_FILE) -> dict[str, pd.DataFrame]:
    """读取并检查最新Wind工作簿的必要Sheet。"""

    if not path.exists():
        raise FileNotFoundError(f"未找到原始工作簿：{path}")
    books = pd.read_excel(path, sheet_name=None)
    required = {
        "Index_Info", "Index_Daily", "Constituents_Weights", "Underlying_Map",
        "Underlying_Daily", "Product_Info", "Selection_Audit", "Launch_Materials",
    }
    missing = sorted(required.difference(books))
    if missing:
        raise ValueError(f"工作簿缺少Sheet：{','.join(missing)}")
    if GT01_SUPPLEMENT_FILE.exists():
        supplement = pd.read_excel(GT01_SUPPLEMENT_FILE, sheet_name=0)
        extraction_date = pd.Timestamp.fromtimestamp(
            GT01_SUPPLEMENT_FILE.stat().st_mtime
        ).normalize()
        books["Index_Daily"] = merge_gt01_daily_rows(
            books["Index_Daily"],
            supplement,
            extraction_date=extraction_date,
        )
    return reconcile_article_universe(books)


def build_price_series(cleaned: pd.DataFrame) -> dict[str, pd.Series]:
    """把清洗后长表转为指数代码到实际更新日点位的映射。"""

    return {
        str(code): clean_prices(group.set_index("日期")["收盘价"])
        for code, group in cleaned.groupby("Wind代码", sort=False)
    }


def _safe_metrics(series: pd.Series | None) -> dict[str, object]:
    empty = {
        "start_date": pd.NaT, "end_date": pd.NaT, "observations": 0,
        "years": np.nan, "annual_return": np.nan, "annual_volatility": np.nan,
        "max_drawdown": np.nan, "sharpe_daily": np.nan,
    }
    if series is None or len(series) < 2:
        return empty
    try:
        return performance_metrics(series, annual_risk_free_rate=RISK_FREE_RATE)
    except (ValueError, ZeroDivisionError, OverflowError):
        return empty


def _prefixed_metrics(prefix: str, metrics: dict[str, object]) -> dict[str, object]:
    return {
        f"{prefix}起始日": metrics.get("start_date", pd.NaT),
        f"{prefix}截止日": metrics.get("end_date", pd.NaT),
        f"{prefix}观测数": metrics.get("observations", 0),
        f"{prefix}年数": metrics.get("years", np.nan),
        f"{prefix}年化收益": metrics.get("annual_return", np.nan),
        f"{prefix}年化波动": metrics.get("annual_volatility", np.nan),
        f"{prefix}最大回撤": metrics.get("max_drawdown", np.nan),
        f"{prefix}夏普": metrics.get("sharpe_daily", np.nan),
    }


def calculate_universe_metrics(
    info: pd.DataFrame,
    series_by_code: dict[str, pd.Series],
    audit: pd.DataFrame,
) -> pd.DataFrame:
    """计算29只指数的全历史与发布前后统一口径指标。"""

    meta = info.copy()
    for column in ("发布日期", "基期", "摘牌日期"):
        if column in meta:
            meta[column] = pd.to_datetime(meta[column], errors="coerce").dt.normalize()
    audit_lookup = audit.set_index("Wind代码") if not audit.empty else pd.DataFrame()
    rows: list[dict[str, object]] = []
    for _, item in meta.iterrows():
        code = str(item["Wind代码"])
        series = series_by_code.get(code)
        publication = item.get("发布日期", pd.NaT)
        all_metrics = _safe_metrics(series)
        pre_metrics = _safe_metrics(None)
        post_metrics = _safe_metrics(None)
        anchor = pd.NaT
        if series is not None and len(series) >= 2 and pd.notna(publication):
            try:
                pre, post, anchor = split_at_publication(series, publication)
                # 发布日等于首个点时，公开序列不存在可比的回溯段。
                if len(pre) >= 2 and pre.index[0] < anchor:
                    pre_metrics = _safe_metrics(pre)
                post_metrics = _safe_metrics(post)
            except ValueError:
                pass
        if code in audit_lookup.index:
            status = str(audit_lookup.loc[code, "数据状态"])
            end_date = audit_lookup.loc[code, "计算截止日"]
        else:
            status = "无行情" if series is None else "正常更新"
            end_date = all_metrics.get("end_date", pd.NaT)
        if series is None:
            declared_status = item.get("数据状态", np.nan)
            status = (
                str(declared_status)
                if pd.notna(declared_status) and str(declared_status).strip()
                else "无行情"
            )

        row: dict[str, object] = {
            "文章序号": ARTICLE_ORDER.index(code) + 1 if code in ARTICLE_ORDER else np.nan,
            "Wind代码": code,
            "证券简称": item.get("证券简称", ""),
            "发布日期": publication,
            "基期": item.get("基期", pd.NaT),
            "收益处理方式": item.get("收益处理方式", "未说明"),
            "发布机构": item.get("发布机构", ""),
            "发布切分锚点": anchor,
            "计算截止日": end_date,
            "数据状态": status,
            "公众号判断": ARTICLE_JUDGEMENT.get(code, "停更/数据不足"),
            "公众号分组": (
                "19只发布前后比较"
                if code in ARTICLE_COMPARABLE
                else ("3只公开运行记录" if code in ARTICLE_PUBLIC_RECORD else "7只停更/数据不足")
            ),
        }
        row.update(_prefixed_metrics("全历史", all_metrics))
        row.update(_prefixed_metrics("发布前", pre_metrics))
        row.update(_prefixed_metrics("发布后", post_metrics))
        pre_return = row["发布前年化收益"]
        post_return = row["发布后年化收益"]
        pre_sharpe = row["发布前夏普"]
        post_sharpe = row["发布后夏普"]
        row["收益差"] = (
            float(pre_return) - float(post_return)
            if pd.notna(pre_return) and pd.notna(post_return) else np.nan
        )
        row["夏普差"] = (
            float(pre_sharpe) - float(post_sharpe)
            if pd.notna(pre_sharpe) and pd.notna(post_sharpe) else np.nan
        )
        row["复算判断"] = article_style_judgement(row)
        row["项目评价"] = project_comment(row)
        if code in ARTICLE_PUBLIC_RECORD and pd.notna(row["发布前年化收益"]):
            row["项目评价"] = (
                "公众号原文缺发布前数据；本次Wind已含回溯序列，"
                "说明数据版本可能后续补充，复算仅作新增证据。"
            )
        if code in ARTICLE_SPECIAL:
            if code == "CALLWE.WI":
                row["项目评价"] = "确认停更且无行情；保留在29只母样本中，不进入绩效计算。"
            else:
                row["项目评价"] = (
                    "公众号将其归入停更/数据不足组；"
                    + (
                        "本次Wind已有序列，仅作补充复算，不纳入原文19只正式比较。"
                        if series is not None
                        else "Wind仍无行情，保留占位。"
                    )
                )
        rows.append(row)
    result = pd.DataFrame(rows).sort_values("文章序号").reset_index(drop=True)
    return result


def select_simplified_chinese_font() -> tuple[str, Path]:
    """加载简体苹方，明确拒绝PingFang HK。"""

    if not PINGFANG_COLLECTION.exists():
        raise FileNotFoundError(f"未找到苹方字体集：{PINGFANG_COLLECTION}")
    if not PINGFANG_SC_REGULAR.exists():
        from fontTools.ttLib import TTCollection

        PINGFANG_SC_REGULAR.parent.mkdir(parents=True, exist_ok=True)
        collection = TTCollection(PINGFANG_COLLECTION)
        collection.fonts[3].save(PINGFANG_SC_REGULAR)
        collection.close()
    fm.fontManager.addfont(PINGFANG_SC_REGULAR)
    family = fm.FontProperties(fname=PINGFANG_SC_REGULAR).get_name()
    if family not in {"PingFang SC", "苹方-简"} or "HK" in family.upper():
        raise RuntimeError(f"加载的不是简体苹方：{family}")
    return family, PINGFANG_SC_REGULAR


def configure_charts() -> None:
    family, _ = select_simplified_chinese_font()
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [family],
            "axes.unicode_minus": False,
            "figure.facecolor": CHART_STYLE["figure_facecolor"],
            "axes.facecolor": CHART_STYLE["axes_facecolor"],
            "axes.edgecolor": CHART_STYLE["spine"],
            "axes.linewidth": 0.7,
            "axes.titleweight": "normal",
            "axes.titlesize": 13,
            "axes.titlepad": 8,
            "axes.labelsize": 10,
            "axes.labelcolor": CHART_STYLE["text"],
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "xtick.color": CHART_STYLE["muted_text"],
            "ytick.color": CHART_STYLE["muted_text"],
            "text.color": CHART_STYLE["text"],
            "grid.color": CHART_STYLE["grid"],
            "grid.linewidth": 0.7,
            "grid.alpha": 0.20,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "savefig.dpi": 180,
            "savefig.facecolor": CHART_STYLE["figure_facecolor"],
            "savefig.edgecolor": CHART_STYLE["figure_facecolor"],
            "savefig.transparent": False,
        }
    )


def style_axes(ax: plt.Axes, grid_axis: str | None = None) -> None:
    """应用统一的研报绘图区、弱网格和轻量坐标轴。"""

    ax.set_facecolor(CHART_STYLE["axes_facecolor"])
    ax.set_axisbelow(True)
    ax.grid(False)
    if grid_axis is not None:
        ax.grid(
            True,
            axis=grid_axis,
            which="major",
            color=CHART_STYLE["grid"],
            linewidth=0.7,
            alpha=0.20,
        )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(CHART_STYLE["spine"])
        ax.spines[side].set_linewidth(0.7)
    ax.tick_params(axis="both", colors=CHART_STYLE["muted_text"], width=0.7)


def _new_page(title: str, subtitle: str = "") -> tuple[plt.Figure, plt.Axes]:
    """创建只承载图表的画布；subtitle参数仅为兼容旧调用，不再绘制。"""

    fig, ax = plt.subplots(figsize=(12, 6.3), facecolor=CHART_STYLE["figure_facecolor"])
    fig.patch.set_facecolor(CHART_STYLE["figure_facecolor"])
    fig.subplots_adjust(left=0.10, right=0.96, top=0.86, bottom=0.14)
    fig.suptitle(
        title,
        x=0.08,
        y=0.945,
        ha="left",
        fontsize=17,
        fontweight="normal",
        color=CHART_STYLE["text"],
    )
    style_axes(ax)
    return fig, ax


def _footnote(fig: plt.Figure, text: str = "数据来源：Wind") -> None:
    """PNG只保留用户指定的数据来源文字。"""

    fig.text(
        0.08,
        0.028,
        text,
        fontsize=7.5,
        color=CHART_STYLE["muted_text"],
        ha="left",
    )


def _save(fig: plt.Figure, filename: str) -> Path:
    path = FIGURES / filename
    fig.patch.set_facecolor(CHART_STYLE["figure_facecolor"])
    fig.savefig(
        path,
        bbox_inches="tight",
        facecolor=CHART_STYLE["figure_facecolor"],
        edgecolor=CHART_STYLE["figure_facecolor"],
        transparent=False,
    )
    plt.close(fig)
    return path


def _pct(value: object, digits: int = 1) -> str:
    return "—" if pd.isna(value) else f"{float(value):.{digits}%}"


def _num(value: object, digits: int = 2) -> str:
    return "—" if pd.isna(value) else f"{float(value):.{digits}f}"


def _years(value: object) -> str:
    return "—" if pd.isna(value) else f"{float(value):.1f}年"


def _short_name(name: object, limit: int = 16) -> str:
    text = str(name).replace("指数", "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def markdown_table(frame: pd.DataFrame, columns: list[str] | tuple[str, ...]) -> str:
    """把DataFrame渲染为原生Markdown表格，不把表格烘焙进PNG。"""

    def escape(value: object) -> str:
        if pd.isna(value):
            return "—"
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    selected = frame.loc[:, list(columns)]
    header = "| " + " | ".join(map(str, columns)) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = [
        "| " + " | ".join(escape(value) for value in row) + " |"
        for row in selected.itertuples(index=False, name=None)
    ]
    return "\n".join([header, divider, *rows])


def _universe_markdown_table(metrics: pd.DataFrame) -> str:
    """按研究分组展示29只指数，不在样本清单页提前混入绩效判断。"""

    required = {"文章序号", "Wind代码", "证券简称", "公众号分组"}
    missing = required.difference(metrics.columns)
    if missing:
        raise KeyError(f"29只样本清单缺少字段：{sorted(missing)}")
    if len(metrics) != 29 or metrics["Wind代码"].nunique() != 29:
        raise AssertionError("29只样本清单必须包含29个不重复的Wind代码")

    expected_counts = {
        "19只发布前后比较": 19,
        "3只公开运行记录": 3,
        "7只停更/数据不足": 7,
    }
    actual_counts = metrics["公众号分组"].value_counts().to_dict()
    if actual_counts != expected_counts:
        raise AssertionError(f"29只样本分组应为19/3/7，实际为{actual_counts}")

    ordered = metrics.sort_values("文章序号").copy()

    def group_rows(group: str) -> list[str]:
        rows = ordered.loc[ordered["公众号分组"] == group]
        return [
            f"{int(row['文章序号'])}. {_short_name(row['证券简称'], 16)}"
            f"<br><small>{row['Wind代码']}</small>"
            for _, row in rows.iterrows()
        ]

    comparison = group_rows("19只发布前后比较")
    public_record = group_rows("3只公开运行记录")
    special = group_rows("7只停更/数据不足")
    columns = {
        "发布前后比较①": comparison[:10],
        "发布前后比较②": comparison[10:],
        "公开运行记录（3只）": public_record,
        "停更/数据不足（7只）": special,
    }
    row_count = max(len(values) for values in columns.values())
    table = pd.DataFrame(
        {
            heading: values + [""] * (row_count - len(values))
            for heading, values in columns.items()
        }
    )
    return markdown_table(table, list(columns))


def _underlying_proxy_summary(books: dict[str, pd.DataFrame], code: str) -> str:
    """用2025年底层工具收益做方向性线索，不冒充指数归因。"""

    daily = books["Underlying_Daily"].copy()
    if daily.empty or code not in set(daily["所属指数"].dropna().astype(str)):
        return "无可用底层行情，不做收益来源推断。"
    date_candidates = [column for column in daily.columns if "每日收盘价时间" in str(column)]
    price_candidates = [
        column for column in daily.columns
        if "每日收盘价" in str(column) and "时间" not in str(column)
    ]
    if len(date_candidates) != 1 or len(price_candidates) != 1:
        raise ValueError("Underlying_Daily无法唯一识别日期与收盘价字段")
    date_col = date_candidates[0]
    price_col = price_candidates[0]
    part = daily.loc[daily["所属指数"].astype(str) == code].copy()
    part[date_col] = pd.to_datetime(part[date_col], errors="coerce")
    part[price_col] = pd.to_numeric(part[price_col], errors="coerce")
    returns: list[tuple[str, float]] = []
    for _, group in part.groupby("Wind代码"):
        series = clean_prices(group.set_index(date_col)[price_col]).loc["2024-12-31":"2025-12-31"]
        if len(series) >= 2 and (series.index[-1] - series.index[0]).days >= 250:
            name = str(group["证券简称"].dropna().iloc[0])
            returns.append((name, float(series.iloc[-1] / series.iloc[0] - 1)))
    if not returns:
        return "有底层名单，但2025年行情不足以形成可比线索。"
    top = sorted(returns, key=lambda item: item[1], reverse=True)[:3]
    labels = "、".join(f"{name}({_pct(value, 0)})" for name, value in top)
    return f"2025年底层工具中涨幅居前的是{labels}；因缺权重，这只是驱动线索，不是贡献归因。"


def build_evidence_matrix(books: dict[str, pd.DataFrame], metrics: pd.DataFrame) -> pd.DataFrame:
    selection = books["Selection_Audit"].set_index("Wind代码")
    launches = books["Launch_Materials"].copy()
    launches["日期"] = pd.to_datetime(launches["日期"], errors="coerce")
    products = books["Product_Info"].set_index("指数代码")
    constituent = books["Constituents_Weights"]
    metric_lookup = metrics.set_index("Wind代码")
    rows: list[dict[str, object]] = []
    for code in FOCUS_CODES:
        s = selection.loc[code]
        launch = launches.loc[launches["Wind代码"] == code].copy()
        found = launch.loc[~launch["材料名称"].astype(str).str.contains("未检索|非同一")]
        if found.empty:
            launch_text = "未找到公开方法书或发行同期研报。"
        else:
            pieces = []
            publication = metric_lookup.loc[code, "发布日期"]
            for _, material in found.sort_values("日期").head(2).iterrows():
                label = "日期待核"
                if pd.notna(material["日期"]) and pd.notna(publication):
                    lag = (material["日期"] - publication).days / 365.2425
                    label = "发行同期" if abs(lag) <= 1 else f"发布后{lag:.1f}年"
                material_type = str(material["材料类型"])
                if label.startswith("发布后"):
                    material_type = material_type.replace("发行同期", "后续")
                pieces.append(f"{material_type}({label})")
            launch_text = "、".join(pieces) + "；不将后续材料倒推为发行时规则。"
        product = products.loc[code]
        weight_count = int(
            constituent.loc[constituent["指数代码"] == code, "权重(%)"].notna().sum()
        )
        component_count = int(
            constituent.loc[constituent["指数代码"] == code, "成分代码"].nunique()
        )
        component_text = (
            f"Wind有{component_count}个历史成分代码，可用权重{weight_count}条。"
            if component_count else "Wind未返回历史成分与权重。"
        )
        rows.append(
            {
                "Wind代码": code,
                "证券简称": metric_lookup.loc[code, "证券简称"],
                "资产选择证据": s.get("真实资产类别", "待核验"),
                "资产核验来源": s.get("核验证据", ""),
                "成分与权重": component_text,
                "发行/方法材料": launch_text,
                "产品情况": f"{product.get('产品类型', '待核验')}：{product.get('产品名称', '待核验')}",
                "底层驱动线索": _underlying_proxy_summary(books, code),
                "可投资性边界": "缺产品净值、费用、交易成本与跟踪误差，指数收益不等于客户净收益。",
            }
        )
    return pd.DataFrame(rows)


def export_results(
    books: dict[str, pd.DataFrame],
    cleaned_audit: pd.DataFrame,
    metrics: pd.DataFrame,
    evidence: pd.DataFrame,
) -> list[Path]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    selection = books["Selection_Audit"][["Wind代码", "是否覆盖两个以上大类资产", "异常状态"]]
    quality = metrics[["Wind代码", "证券简称", "公众号分组", "数据状态", "计算截止日"]].merge(
        cleaned_audit, on=["Wind代码", "证券简称"], how="left", suffixes=("", "_清洗")
    ).merge(selection, on="Wind代码", how="left")
    comparison = metrics.loc[metrics["公众号分组"] == "19只发布前后比较"].copy()
    outputs = [
        (quality, RESULTS / "答辩重构_29指数数据质量.csv"),
        (metrics, RESULTS / "答辩重构_29指数统一绩效.csv"),
        (comparison, RESULTS / "答辩重构_29指数发布前后比较.csv"),
        (evidence, RESULTS / "答辩重构_四指数证据矩阵.csv"),
    ]
    for frame, path in outputs:
        frame.to_csv(path, index=False, encoding="utf-8-sig")
    return [path for _, path in outputs]


def make_sample_structure_figure(metrics: pd.DataFrame) -> plt.Figure:
    """用两条100%横向堆叠条展示母样本与统一复算结果。"""

    formal = metrics.loc[
        (metrics["公众号分组"] == "19只发布前后比较") & metrics["收益差"].notna()
    ]
    rows = [
        {
            "label": "29只母样本",
            "segments": [
                ("前后比较", 19, RESEARCH_COLORS["primary"], "white"),
                ("公开记录", 3, RESEARCH_COLORS["secondary"], "white"),
                ("停更/不足", 7, RESEARCH_COLORS["light_neutral"], CHART_STYLE["text"]),
            ],
        },
        {
            "label": "19只可比样本",
            "segments": [
                ("衰减>2pct", int((formal["复算判断"] == "过拟合").sum()), RESEARCH_COLORS["down"], "white"),
                ("基本一致", int((formal["复算判断"] == "基本一致").sum()), RESEARCH_COLORS["secondary"], "white"),
                ("发布后更好", int((formal["复算判断"] == "样本外更好").sum()), RESEARCH_COLORS["up"], "white"),
            ],
        },
    ]

    fig = plt.figure(figsize=(12, 5.6), facecolor=CHART_STYLE["figure_facecolor"])
    fig.patch.set_facecolor(CHART_STYLE["figure_facecolor"])
    fig.suptitle(
        "29只指数样本结构与统一复算结果",
        x=0.08,
        y=0.93,
        ha="left",
        fontsize=17,
        fontweight="normal",
        color=CHART_STYLE["text"],
    )
    ax = fig.add_axes([0.18, 0.20, 0.76, 0.57])
    y_positions = [1, 0]
    for y, row in zip(y_positions, rows):
        total = sum(value for _, value, _, _ in row["segments"])
        left = 0.0
        for label, value, color, text_color in row["segments"]:
            share = value / total if total else 0.0
            ax.barh(y, share, left=left, color=color, height=0.42)
            annotation = f"{label}\n{value}只（{share:.0%}）"
            if share >= 0.09:
                ax.text(
                    left + share / 2,
                    y,
                    annotation,
                    ha="center",
                    va="center",
                    fontsize=9.2,
                    linespacing=1.2,
                    color=text_color,
                )
            else:
                ax.annotate(
                    annotation,
                    xy=(left + share / 2, y),
                    xytext=(min(left + share + 0.015, 0.985), y + 0.36),
                    ha="right",
                    va="bottom",
                    fontsize=8.7,
                    color=color,
                    arrowprops={"arrowstyle": "-", "color": color, "lw": 0.8},
                )
            left += share

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.55, 1.55)
    ax.set_yticks(y_positions, [row["label"] for row in rows])
    ticks = np.linspace(0, 1, 5)
    ax.set_xticks(ticks, [f"{tick:.0%}" for tick in ticks])
    ax.set_xlabel("组内占比")
    style_axes(ax, "x")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=12)
    _footnote(fig)
    return fig


def plot_sample_structure(metrics: pd.DataFrame) -> Path:
    """生成母样本与统一复算结果的单页图表。"""

    fig = make_sample_structure_figure(metrics)
    return _save(fig, FIGURE_NAMES[0])


def plot_joint_pre_post_changes(metrics: pd.DataFrame) -> Path:
    """按相同行序联合展示每只指数的收益与夏普变化。"""

    frame = metrics.loc[
        (metrics["公众号分组"] == "19只发布前后比较")
        & metrics["发布前年化收益"].notna()
        & metrics["发布后年化收益"].notna()
        & metrics["发布前夏普"].notna()
        & metrics["发布后夏普"].notna()
    ].copy()
    frame = frame.sort_values("收益差", ascending=False).reset_index(drop=True)
    y = np.arange(len(frame))

    fig = plt.figure(figsize=(12, 6.3), facecolor=CHART_STYLE["figure_facecolor"])
    fig.patch.set_facecolor(CHART_STYLE["figure_facecolor"])
    fig.suptitle(
        "发布前后收益与夏普联合变化",
        x=0.08,
        y=0.945,
        ha="left",
        fontsize=17,
        fontweight="normal",
        color=CHART_STYLE["text"],
    )
    ax_return = fig.add_axes([0.18, 0.14, 0.34, 0.72])
    ax_sharpe = fig.add_axes([0.60, 0.14, 0.34, 0.72])

    for ax, pre_col, post_col, title, is_pct in [
        (ax_return, "发布前年化收益", "发布后年化收益", "年化收益", True),
        (ax_sharpe, "发布前夏普", "发布后夏普", "夏普比率", False),
    ]:
        for row_index, row in frame.iterrows():
            pre = float(row[pre_col])
            post = float(row[post_col])
            color = RESEARCH_COLORS["down"] if post < pre else RESEARCH_COLORS["up"]
            ax.annotate(
                "",
                xy=(post, row_index),
                xytext=(pre, row_index),
                arrowprops={"arrowstyle": "-|>", "color": color, "lw": 1.5, "mutation_scale": 8},
                zorder=2,
            )
            ax.scatter(
                pre,
                row_index,
                s=34,
                facecolors=CHART_STYLE["axes_facecolor"],
                edgecolors=color,
                linewidths=1.2,
                zorder=3,
            )
            ax.scatter(post, row_index, s=38, color=color, zorder=4)
        ax.set_title(title, loc="left")
        ax.axvline(0, color=CHART_STYLE["spine"], lw=0.7)
        ax.set_ylim(len(frame) - 0.4, -0.6)
        style_axes(ax, "x")
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0, labelsize=7.8)
        if is_pct:
            ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))

    ax_return.set_yticks(y, [_short_name(name, 18) for name in frame["证券简称"]])
    ax_sharpe.set_yticks(y, [])
    ax_return.plot([], [], color=RESEARCH_COLORS["down"], lw=2, label="发布后下降")
    ax_return.plot([], [], color=RESEARCH_COLORS["up"], lw=2, label="发布后上升")
    ax_return.scatter(
        [], [], s=34, facecolors=CHART_STYLE["axes_facecolor"],
        edgecolors=CHART_STYLE["muted_text"], label="发布前",
    )
    ax_return.scatter([], [], s=38, color=CHART_STYLE["muted_text"], label="发布后")
    handles, labels = ax_return.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.62, 0.025),
        ncol=4,
    )
    _footnote(fig)
    return _save(fig, FIGURE_NAMES[1])


def plot_decay_ranking(metrics: pd.DataFrame) -> Path:
    frame = metrics.loc[
        (metrics["公众号分组"] == "19只发布前后比较") & metrics["收益差"].notna()
    ].nlargest(10, "收益差").sort_values("收益差", ascending=False).reset_index(drop=True)
    frame["收益变化"] = frame["发布后年化收益"] - frame["发布前年化收益"]
    frame["夏普变化"] = frame["发布后夏普"] - frame["发布前夏普"]
    # 四列统一为“正值=改善、负值=变差”，避免风险指标的方向语义与收益相反。
    frame["波动改善"] = frame["发布前年化波动"] - frame["发布后年化波动"]
    frame["最大回撤改善"] = frame["发布前最大回撤"].abs() - frame["发布后最大回撤"].abs()
    columns = ["收益变化", "夏普变化", "波动改善", "最大回撤改善"]
    raw = frame[columns].to_numpy(float)
    scale = np.nanmax(np.abs(raw), axis=0)
    scale[scale == 0] = 1.0
    normalized = raw / scale

    fig = plt.figure(figsize=(12, 6.3), facecolor=CHART_STYLE["figure_facecolor"])
    fig.patch.set_facecolor(CHART_STYLE["figure_facecolor"])
    fig.suptitle(
        "收益衰减前十的多维诊断",
        x=0.08,
        y=0.945,
        ha="left",
        fontsize=17,
        fontweight="normal",
        color=CHART_STYLE["text"],
    )
    ax_heat = fig.add_axes([0.24, 0.17, 0.50, 0.68])
    ax_years = fig.add_axes([0.79, 0.17, 0.16, 0.68])
    cmap = mpl.colors.LinearSegmentedColormap.from_list(
        "research_diverging",
        [RESEARCH_COLORS["worse"], CHART_STYLE["axes_facecolor"], RESEARCH_COLORS["better"]],
    )
    image = ax_heat.imshow(normalized, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
    ax_heat.set_xticks(
        np.arange(4),
        [
            "收益变化\n（上升为正）",
            "夏普变化\n（上升为正）",
            "波动改善\n（下降为正）",
            "最大回撤改善\n（收窄为正）",
        ],
    )
    ax_heat.set_yticks(
        np.arange(len(frame)),
        [_short_name(name, 20) for name in frame["证券简称"]],
    )
    formatters = [lambda x: f"{x:.1%}", lambda x: f"{x:.2f}", lambda x: f"{x:.1%}", lambda x: f"{x:.1%}"]
    for row_index in range(len(frame)):
        for col_index in range(4):
            value = raw[row_index, col_index]
            text_color = "white" if abs(normalized[row_index, col_index]) >= 0.58 else CHART_STYLE["text"]
            ax_heat.text(
                col_index,
                row_index,
                formatters[col_index](value),
                ha="center",
                va="center",
                fontsize=8.5,
                color=text_color,
            )
    ax_heat.tick_params(axis="x", top=True, bottom=False, labeltop=True, labelbottom=False, length=0)
    ax_heat.tick_params(axis="y", length=0, labelsize=8.2)
    for spine in ax_heat.spines.values():
        spine.set_visible(False)
    colorbar = fig.colorbar(image, ax=ax_heat, orientation="horizontal", fraction=0.035, pad=0.07)
    colorbar.set_ticks([-1, 0, 1], labels=["变差", "不变", "变好"])
    colorbar.outline.set_visible(False)

    years = frame["发布后年数"].to_numpy(float)
    for row_index, (_, row) in enumerate(frame.iterrows()):
        stopped = "停更" in str(row["数据状态"])
        short = float(row["发布后年数"]) < 1
        marker = "X" if stopped else "o"
        color = RESEARCH_COLORS["accent"] if short else RESEARCH_COLORS["secondary"]
        ax_years.scatter(float(row["发布后年数"]), row_index, s=52, marker=marker, color=color, zorder=3)
    ax_years.axvline(1.0, color=RESEARCH_COLORS["accent"], linestyle="--", lw=1.0, label="1年")
    ax_years.set_xlim(0, max(5.5, float(np.nanmax(years)) + 0.5))
    ax_years.set_ylim(len(frame) - 0.5, -0.5)
    ax_years.set_yticks([])
    ax_years.set_title("发布后年数", loc="left")
    style_axes(ax_years, "x")
    ax_years.spines["left"].set_visible(False)
    ax_years.scatter([], [], s=45, marker="o", color=RESEARCH_COLORS["accent"], label="不足1年")
    ax_years.scatter([], [], s=45, marker="X", color=RESEARCH_COLORS["secondary"], label="已停更")
    ax_years.legend(loc="lower right")
    _footnote(fig)
    return _save(fig, FIGURE_NAMES[2])


def plot_article_recalculation(metrics: pd.DataFrame) -> Path:
    lookup = metrics.set_index("Wind代码")
    rows = []
    for (code, period), values in ARTICLE_FOCUS.items():
        annual_return, _, _, sharpe = values
        prefix = {"pre": "发布前", "post": "发布后", "all": "全历史"}[period]
        frequency = ARTICLE_SHARPE_FREQUENCY.get((code, period), "日频/未单独标注")
        frequency_tag = "（原文月频）" if frequency == "月频" else ""
        rows.append(
            {
                "label": f"{code.split('.')[0]}-{ {'pre':'前','post':'后','all':'全'}[period] }{frequency_tag}",
                "frequency": frequency,
                "article_return": annual_return,
                "recalc_return": lookup.loc[code, f"{prefix}年化收益"],
                "article_sharpe": sharpe,
                "recalc_sharpe": lookup.loc[code, f"{prefix}夏普"],
            }
        )
    frame = pd.DataFrame(rows)
    fig = plt.figure(figsize=(12, 6.3), facecolor=CHART_STYLE["figure_facecolor"])
    fig.patch.set_facecolor(CHART_STYLE["figure_facecolor"])
    fig.suptitle(
        "原文口径与统一日频复算差异",
        x=0.08,
        y=0.945,
        ha="left",
        fontsize=17,
        fontweight="normal",
        color=CHART_STYLE["text"],
    )
    ax1 = fig.add_axes([0.13, 0.15, 0.37, 0.70])
    ax2 = fig.add_axes([0.59, 0.15, 0.35, 0.70])
    y = np.arange(len(frame))
    for ax, article_col, recalc_col, title, is_pct in [
        (ax1, "article_return", "recalc_return", "年化收益", True),
        (ax2, "article_sharpe", "recalc_sharpe", "夏普比率", False),
    ]:
        bars_original = ax.barh(
            y - 0.17,
            frame[article_col],
            height=0.28,
            color=RESEARCH_COLORS["purple"],
            label="原文值",
        )
        bars_recalc = ax.barh(
            y + 0.17,
            frame[recalc_col],
            height=0.28,
            color=RESEARCH_COLORS["primary"],
            label="统一日频复算",
        )
        for row_index, bar in enumerate(bars_original):
            if frame.loc[row_index, "frequency"] == "月频":
                bar.set_hatch("////")
                bar.set_edgecolor("white")
        for bars, column in ((bars_original, article_col), (bars_recalc, recalc_col)):
            for row_index, bar in enumerate(bars):
                value = float(frame.loc[row_index, column])
                label = f"{value:.1%}" if is_pct else f"{value:.2f}"
                ax.text(
                    value,
                    bar.get_y() + bar.get_height() / 2,
                    f" {label}",
                    va="center",
                    fontsize=7.8,
                    color=CHART_STYLE["text"],
                )
        ax.set_yticks(y, frame["label"] if ax is ax1 else [])
        ax.set_title(title, loc="left")
        ax.set_ylim(len(frame) - 0.45, -0.55)
        ax.axvline(0, color=CHART_STYLE["spine"], lw=0.7)
        style_axes(ax, "x")
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0, labelsize=7.8)
        if is_pct:
            ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
        ax.margins(x=0.12)
    ax1.legend(loc="lower right")
    _footnote(fig, "数据来源：Wind、公众号原文")
    return _save(fig, FIGURE_NAMES[3])


def plot_focus_comparison(
    metrics: pd.DataFrame,
    series_by_code: dict[str, pd.Series],
) -> Path:
    """输出四只重点指数的全历史归一化走势。"""

    fig, ax = _new_page("4只重点指数全历史走势")
    lookup = metrics.set_index("Wind代码")
    for code in FOCUS_CODES:
        series = series_by_code[code]
        normalized = series / series.iloc[0] * 100
        color = FOCUS_COLORS[code]
        ax.plot(normalized.index, normalized, lw=2.0, color=color, label=code.split(".")[0])
        publication = pd.Timestamp(lookup.loc[code, "发布日期"])
        before = normalized.loc[normalized.index <= publication]
        if not before.empty:
            ax.scatter(
                before.index[-1],
                before.iloc[-1],
                s=52,
                facecolors=CHART_STYLE["axes_facecolor"],
                edgecolors=color,
                linewidths=1.4,
                zorder=5,
            )
    ax.set_ylabel("指数点位（各自起点=100）")
    style_axes(ax, "both")
    ax.legend(loc="upper left", ncol=2)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _footnote(fig)
    return _save(fig, FIGURE_NAMES[4])


def _case_conclusion(code: str, row: pd.Series) -> tuple[str, str]:
    if code == "CI011800.WI":
        return (
            "发布后改善明确，但收益来源和可持续性尚未识别",
            f"统一复算下收益由{_pct(row['发布前年化收益'])}升至{_pct(row['发布后年化收益'])}、"
            f"夏普由{_num(row['发布前夏普'])}升至{_num(row['发布后夏普'])}，而最大回撤基本未收窄。"
            f"这构成对“发布后普遍失效”的强反例；但发布前仅{_num(row['发布前年数'], 2)}年"
            "且无历史权重，不能把高收益归因于某一资产或确认可以延续。",
        )
    if code == "CICSF040.WI":
        return (
            "长期风险收益记录突出，但不是样本内外识别",
            f"{_num(row['全历史年数'], 1)}年公开记录的年化收益{_pct(row['全历史年化收益'])}、"
            f"最大回撤{_pct(abs(row['全历史最大回撤']))}、统一日频夏普{_num(row['全历史夏普'])}均较强。"
            "但基日等于发布日期只能证明公开序列没有发布前回溯段，不能证明研发阶段未查看历史数据或未调参。",
        )
    if code == "CI011001.WI":
        return (
            "七年发布后记录稳定，是四只中证据最完整的反例",
            f"发布后收益由{_pct(row['发布前年化收益'])}升至{_pct(row['发布后年化收益'])}、"
            f"夏普由{_num(row['发布前夏普'])}升至{_num(row['发布后夏普'])}、"
            f"最大回撤由{_pct(abs(row['发布前最大回撤']))}收窄至{_pct(abs(row['发布后最大回撤']))}。"
            "改善幅度不算巨大，但持续时间足够长；原文提出的市场环境解释合理，却仍缺权重和状态归因支持。",
        )
    if code == "GALLW.WI":
        return (
            "收益、夏普、波动和回撤同时恶化，但样本仍太短",
            f"统一复算下收益由{_pct(row['发布前年化收益'])}降至{_pct(row['发布后年化收益'])}、"
            f"夏普由{_num(row['发布前夏普'])}降至{_num(row['发布后夏普'])}、"
            f"波动由{_pct(row['发布前年化波动'])}升至{_pct(row['发布后年化波动'])}，回撤也扩大。"
            f"多维恶化比单看收益更值得警惕，但发布后仅{_num(row['发布后年数'], 2)}年，"
            "尚不足以确认策略长期失效或过拟合因果。",
        )
    raise KeyError(f"未定义的重点指数：{code}")


def plot_case_page(
    code: str,
    metrics: pd.DataFrame,
    series_by_code: dict[str, pd.Series],
    evidence: pd.DataFrame,
    filename: str,
) -> Path:
    """输出单只指数的发布前后纯走势图。"""

    row = metrics.set_index("Wind代码").loc[code]
    _ = evidence
    fig, ax_plot = _new_page(f"{row['证券简称']}发布前后走势")
    series = series_by_code[code]
    normalized = series / series.iloc[0] * 100
    publication = pd.Timestamp(row["发布日期"])
    anchor = row["发布切分锚点"]
    if pd.notna(anchor) and anchor > series.index[0]:
        pre = normalized.loc[:anchor]
        ax_plot.plot(
            pre.index,
            pre,
            color=RESEARCH_COLORS["neutral"],
            lw=1.8,
            label="发布前回溯期",
        )
        post = normalized.loc[anchor:]
    else:
        post = normalized
    ax_plot.plot(post.index, post, color=FOCUS_COLORS[code], lw=2.3, label="发布后运行期")
    ax_plot.axvline(
        publication,
        color=CHART_STYLE["muted_text"],
        linestyle="--",
        lw=0.9,
    )
    ax_plot.scatter(
        post.index[0],
        post.iloc[0],
        s=52,
        facecolors=CHART_STYLE["axes_facecolor"],
        edgecolors=FOCUS_COLORS[code],
        linewidths=1.4,
        zorder=5,
        label="发布切分锚点",
    )
    ax_plot.set_ylabel("指数点位（起点=100）")
    style_axes(ax_plot, "both")
    ax_plot.legend(loc="upper left")
    span_years = (series.index[-1] - series.index[0]).days / 365.2425
    if span_years <= 4:
        locator = mdates.MonthLocator(interval=6)
        formatter = mdates.DateFormatter("%Y-%m")
    elif span_years <= 8:
        locator = mdates.YearLocator()
        formatter = mdates.DateFormatter("%Y")
    else:
        locator = mdates.YearLocator(2)
        formatter = mdates.DateFormatter("%Y")
    ax_plot.xaxis.set_major_locator(locator)
    ax_plot.xaxis.set_major_formatter(formatter)
    _footnote(fig)
    return _save(fig, filename)


def plot_decay_sensitivity(metrics: pd.DataFrame) -> Path:
    """检验收益衰减结论对阈值和短样本的敏感性。"""

    frame = metrics.loc[
        (metrics["公众号分组"] == "19只发布前后比较")
        & metrics["收益差"].notna()
    ].copy()
    long_sample = frame.loc[frame["发布后年数"] >= 1].copy()
    thresholds = np.arange(0.00, 0.061, 0.01)
    all_share = np.array([(frame["收益差"] > threshold).mean() for threshold in thresholds])
    long_share = np.array([(long_sample["收益差"] > threshold).mean() for threshold in thresholds])

    fig, ax = _new_page("收益衰减结论的阈值与样本敏感性")
    ax.plot(
        thresholds,
        all_share,
        color=RESEARCH_COLORS["purple"],
        lw=2.1,
        marker="o",
        ms=5,
        label=f"全部可比样本（{len(frame)}只）",
    )
    ax.plot(
        thresholds,
        long_share,
        color=RESEARCH_COLORS["primary"],
        lw=2.1,
        marker="s",
        ms=5,
        label=f"发布后≥1年（{len(long_sample)}只）",
    )
    ax.axvline(
        0.02,
        color=RESEARCH_COLORS["purple"],
        linestyle="--",
        lw=1.0,
        alpha=0.8,
    )
    threshold_index = int(np.where(np.isclose(thresholds, 0.02))[0][0])
    all_count = int((frame["收益差"] > 0.02).sum())
    long_count = int((long_sample["收益差"] > 0.02).sum())
    ax.annotate(
        f"{all_count}/{len(frame)}",
        (0.02, all_share[threshold_index]),
        xytext=(8, 8),
        textcoords="offset points",
        fontsize=9,
        color=RESEARCH_COLORS["purple"],
    )
    ax.annotate(
        f"{long_count}/{len(long_sample)}",
        (0.02, long_share[threshold_index]),
        xytext=(8, -14),
        textcoords="offset points",
        fontsize=9,
        color=RESEARCH_COLORS["primary"],
    )
    ax.set_xlabel("收益衰减判定阈值")
    ax.set_ylabel("超过阈值的指数占比")
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlim(-0.002, 0.062)
    ax.set_ylim(0, 0.78)
    style_axes(ax, "both")
    ax.legend(loc="upper right")
    _footnote(fig)
    return _save(fig, FIGURE_NAMES[9])


def generate_all_figures(
    books: dict[str, pd.DataFrame],
    metrics: pd.DataFrame,
    series_by_code: dict[str, pd.Series],
    evidence: pd.DataFrame,
) -> list[Path]:
    """生成10张只含标题、图表和数据来源的PNG。"""

    configure_charts()
    FIGURES.mkdir(parents=True, exist_ok=True)
    for filename in FIGURE_NAMES:
        legacy = LEGACY_FIGURES_DIR / filename
        if legacy.exists():
            legacy.unlink()
    for filename in LEGACY_FIGURE_NAMES:
        legacy = FIGURES / filename
        if legacy.exists():
            legacy.unlink()
    _ = books
    paths: list[Path] = []
    paths.append(plot_sample_structure(metrics))
    paths.append(plot_joint_pre_post_changes(metrics))
    paths.append(plot_decay_ranking(metrics))
    paths.append(plot_article_recalculation(metrics))
    paths.append(plot_focus_comparison(metrics, series_by_code))
    case_filenames = {
        "CI011800.WI": FIGURE_NAMES[5],
        "CICSF040.WI": FIGURE_NAMES[6],
        "CI011001.WI": FIGURE_NAMES[7],
        "GALLW.WI": FIGURE_NAMES[8],
    }
    for code in FOCUS_CODES:
        paths.append(plot_case_page(code, metrics, series_by_code, evidence, case_filenames[code]))
    paths.append(plot_decay_sensitivity(metrics))
    expected = [FIGURES / name for name in FIGURE_NAMES]
    if paths != expected:
        raise AssertionError("图片生成顺序与设计清单不一致")
    if len(paths) != 10 or any(not path.exists() or path.stat().st_size == 0 for path in paths):
        raise AssertionError("未完整生成10张非空PNG")
    if set(FOCUS_CODES).difference(series_by_code):
        raise AssertionError("四只重点指数行情不完整")
    if set(metrics["Wind代码"]) != set(ARTICLE_ORDER):
        raise AssertionError("附录没有完整覆盖29只指数")
    return paths


def validate_markdown_links(markdown: str, report_path: Path = REPORT) -> list[Path]:
    """检查Markdown中所有本地图片链接是否存在。"""

    raw_links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", markdown)
    paths: list[Path] = []
    for raw in raw_links:
        value = raw.strip().strip("<>")
        if re.match(r"^[a-z]+://", value):
            continue
        path = (report_path.parent / value).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Markdown图片链接不存在：{path}")
        paths.append(path)
    return paths


def validate_slide_titles(markdown: str) -> list[str]:
    """确保页面主标题使用客观陈述式语言，且不以公众号为标题主语。"""

    titles = [line[2:].strip() for line in markdown.splitlines() if line.startswith("# ")]
    question_titles = [title for title in titles if "?" in title or "？" in title]
    if question_titles:
        raise AssertionError(f"页面标题应采用客观陈述式语言：{question_titles}")
    article_led_titles = [title for title in titles if "公众号" in title]
    if article_led_titles:
        raise AssertionError(f"页面标题不应以公众号作为叙事主体：{article_led_titles}")
    return titles


def _image_markdown(path: Path, width: int = 720) -> str:
    return f"![w:{width}](./figures/{path.name})"


def _focus_markdown_table(metrics: pd.DataFrame) -> str:
    rows: list[dict[str, str]] = []
    lookup = metrics.set_index("Wind代码")
    for code in FOCUS_CODES:
        row = lookup.loc[code]
        rows.append(
            {
                "指数": f"{_short_name(row['证券简称'], 14)}<br>{code}",
                "收益类型": str(row["收益处理方式"]),
                "前/后年数": f"{_num(row['发布前年数'], 1)}/{_num(row['发布后年数'], 1)}",
                "前/后收益": f"{_pct(row['发布前年化收益'])}/{_pct(row['发布后年化收益'])}",
                "前/后夏普": f"{_num(row['发布前夏普'])}/{_num(row['发布后夏普'])}",
                "复算理解": str(row["复算判断"]),
            }
        )
    columns = ["指数", "收益类型", "前/后年数", "前/后收益", "前/后夏普", "复算理解"]
    return markdown_table(pd.DataFrame(rows), columns)


def _case_metrics_table(row: pd.Series) -> str:
    rows: list[dict[str, str]] = []
    if pd.notna(row["发布前年化收益"]):
        periods = [("发布前回溯期", "发布前"), ("发布后运行期", "发布后")]
    else:
        periods = [("公开运行记录", "全历史")]
    for label, prefix in periods:
        rows.append(
            {
                "区间": label,
                "年数": _years(row[f"{prefix}年数"]),
                "年化收益": _pct(row[f"{prefix}年化收益"]),
                "年化波动": _pct(row[f"{prefix}年化波动"]),
                "最大回撤": _pct(row[f"{prefix}最大回撤"]),
                "夏普": _num(row[f"{prefix}夏普"]),
            }
        )
    columns = ["区间", "年数", "年化收益", "年化波动", "最大回撤", "夏普"]
    return markdown_table(pd.DataFrame(rows), columns)


def _compact_comment(row: pd.Series) -> str:
    if row["Wind代码"] == "CALLWE.WI":
        return "确认停更且无行情；保留在29只母样本中，不进入绩效计算。"
    if "无行情" in str(row["数据状态"]) or "未检索" in str(row["数据状态"]):
        return "无行情，保留占位。"
    if row["公众号分组"] == "7只停更/数据不足":
        return "原文特殊组；补充复算不进入19只。"
    judgement = str(row["复算判断"])
    text = {
        "过拟合": "收益衰减与过拟合担忧一致，非因果证明。",
        "基本一致": "前后收益基本一致。",
        "样本外更好": "发布后更好，不支持“发布即失效”。",
        "暂不判断": "无可比回溯段，仅报告运行记录。",
    }.get(judgement, judgement)
    if pd.notna(row["发布后年数"]) and float(row["发布后年数"]) < 1:
        text += " 后段不足1年。"
    if "停更" in str(row["数据状态"]):
        text += " 已停更。"
    return text


def _appendix_markdown_table(chunk: pd.DataFrame) -> str:
    rows: list[dict[str, str]] = []
    for _, row in chunk.iterrows():
        rows.append(
            {
                "#": str(int(row["文章序号"])),
                "指数": f"{_short_name(row['证券简称'], 13)}<br>{row['Wind代码']}",
                "前/后收益": f"{_pct(row['发布前年化收益'])}/{_pct(row['发布后年化收益'])}",
                "前/后波动": f"{_pct(row['发布前年化波动'])}/{_pct(row['发布后年化波动'])}",
                "前/后回撤": f"{_pct(row['发布前最大回撤'])}/{_pct(row['发布后最大回撤'])}",
                "前/后夏普": f"{_num(row['发布前夏普'])}/{_num(row['发布后夏普'])}",
                "收益差": _pct(row["收益差"]),
                "原文/复算": f"{row['公众号判断']}/{row['复算判断']}",
                "项目评价": _compact_comment(row),
            }
        )
    columns = ["#", "指数", "前/后收益", "前/后波动", "前/后回撤", "前/后夏普", "收益差", "原文/复算", "项目评价"]
    return markdown_table(pd.DataFrame(rows), columns)


def _case_slide(
    number: int,
    code: str,
    metrics: pd.DataFrame,
    evidence: pd.DataFrame,
    image_path: Path,
) -> str:
    row = metrics.set_index("Wind代码").loc[code]
    ev = evidence.set_index("Wind代码").loc[code]
    conclusion_title, conclusion = _case_conclusion(code, row)
    method_evidence = str(ev["发行/方法材料"]).rstrip("。； ")
    source_note = CASE_SOURCE_NOTES[code].rstrip("。； ")
    return f"""<!-- _class: case -->
# [个案{number}] {row['证券简称']}（{code.split('.')[0]}）

{_image_markdown(image_path, 540)}

{_case_metrics_table(row)}

- **资产选择：** {ev['资产选择证据']}；{ev['成分与权重']}
- **发行与方法材料：** {method_evidence}；{source_note}。
- **产品与驱动线索：** {ev['产品情况']}；{ev['底层驱动线索']}
- **原文评价：** {ARTICLE_CASE_EVALUATIONS[code]}

> **本研究评价：{conclusion_title}。** {conclusion} 证据边界：{ev['可投资性边界']}
"""


def render_markdown_deck(
    metrics: pd.DataFrame,
    evidence: pd.DataFrame,
    image_paths: list[Path],
) -> Path:
    """输出19页Marp Markdown答辩稿；图片只负责图，表格和评价留在Markdown。"""

    formal = metrics.loc[
        (metrics["公众号分组"] == "19只发布前后比较") & metrics["收益差"].notna()
    ]
    overfit = int((formal["复算判断"] == "过拟合").sum())
    prices = int(metrics["全历史观测数"].gt(0).sum())
    joint = formal.loc[formal["夏普差"].notna()]
    both_deteriorated = int(((joint["收益差"] > 0) & (joint["夏普差"] > 0)).sum())
    both_improved = int(((joint["收益差"] < 0) & (joint["夏普差"] < 0)).sum())
    mixed_direction = len(joint) - both_deteriorated - both_improved
    top_decay = formal.nlargest(10, "收益差").copy()
    top_decay["波动上升"] = top_decay["发布后年化波动"] - top_decay["发布前年化波动"]
    top_decay["回撤扩大"] = top_decay["发布后最大回撤"].abs() - top_decay["发布前最大回撤"].abs()
    overfit_sharpe_down = int(
        ((formal["收益差"] > 0.02) & (formal["夏普差"] > 0)).sum()
    )
    top_decay_mean = float(top_decay["收益差"].mean())
    top_decay_median = float(top_decay["收益差"].median())
    top_decay_q25 = float(top_decay["收益差"].quantile(0.25))
    top_decay_q75 = float(top_decay["收益差"].quantile(0.75))
    top_over_five = int((top_decay["收益差"] > 0.05).sum())
    top_sharpe_mean = float(top_decay["夏普差"].mean())
    top_sharpe_median = float(top_decay["夏普差"].median())
    top_vol_worse = int((top_decay["波动上升"] > 0).sum())
    top_mdd_worse = int((top_decay["回撤扩大"] > 0).sum())
    top_joint_risk_worse = int(
        ((top_decay["波动上升"] > 0) & (top_decay["回撤扩大"] > 0)).sum()
    )
    top_short = top_decay.loc[top_decay["发布后年数"] < 1]
    top_short_text = "、".join(_short_name(name, 10) for name in top_short["证券简称"])
    top_long = top_decay.loc[top_decay["发布后年数"] >= 1].nlargest(3, "收益差")
    top_long_text = "、".join(_short_name(name, 10) for name in top_long["证券简称"])
    long_sample = formal.loc[formal["发布后年数"] >= 1]
    long_overfit = int((long_sample["收益差"] > 0.02).sum())
    high_threshold_all = int((formal["收益差"] > 0.05).sum())
    high_threshold_long = int((long_sample["收益差"] > 0.05).sum())
    median_decay = float(formal["收益差"].median())
    correlation_frame = formal.dropna(subset=["发布前夏普", "收益差"])
    pearson_correlation = float(correlation_frame["发布前夏普"].corr(correlation_frame["收益差"]))
    spearman_correlation = float(
        correlation_frame["发布前夏普"].rank().corr(correlation_frame["收益差"].rank())
    )
    without_ci011800 = correlation_frame.loc[correlation_frame["Wind代码"] != "CI011800.WI"]
    leave_one_out_correlation = float(
        without_ci011800["发布前夏普"].corr(without_ci011800["收益差"])
    )
    image = {path.name: path for path in image_paths}
    header = """---
marp: true
size: 16:9
paginate: true
theme: default
style: |
  section { background: #F6F2EA; color: #202A34; font-family: 'PingFang SC'; padding: 38px 58px; }
  h1 { color: #202A34; font-size: 35px; margin: 0 0 10px 0; }
  h2 { color: #286983; font-size: 25px; }
  p, li { font-size: 17px; line-height: 1.38; }
  ul, ol { margin-top: 6px; margin-bottom: 6px; }
  blockquote { border-left: 5px solid #C9485B; background: #FFFDF8; padding: 7px 14px; margin: 8px 0; }
  blockquote p { font-size: 15px; line-height: 1.34; }
  img { display: block; margin: 2px auto 6px auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; line-height: 1.22; }
  th { background: #253746; color: white; }
  th, td { border: 1px solid #D5CEC3; padding: 4px 6px; text-align: center; }
  tr:nth-child(even) td { background: #F0ECE4; }
  section.case h1 { font-size: 31px; }
  section.case p, section.case li { font-size: 13px; line-height: 1.25; }
  section.case table { font-size: 11.5px; }
  section.case blockquote p { font-size: 12px; }
  section.universe h1 { font-size: 29px; }
  section.universe table { font-size: 11.3px; line-height: 1.12; }
  section.universe th, section.universe td { padding: 3px 5px; text-align: left; vertical-align: top; }
  section.universe small { color: #6F7880; font-size: 9.5px; }
  section.universe blockquote p { font-size: 12px; }
  section.appendix h1 { font-size: 29px; }
  section.appendix table { font-size: 9.2px; line-height: 1.12; }
  section.appendix th, section.appendix td { padding: 3px 4px; }
---
"""
    slides = [
        f"""<!-- _class: lead -->
# 券商多资产配置指数深度体检

## 29只指数全景比较与4只重点指数分析

**研究目标：** 基于Wind数据检验发布前回溯表现、发布后运行表现及其差异

数据截止：{CUTOFF:%Y-%m-%d}<br>
统一口径可复算 {len(formal)} 只，其中 {overfit} 只收益衰减超过2个百分点
""",
        """# 汇报结构

1. **样本与方法：** 指数筛选、排除标准和发布前后切分口径。
2. **全景比较：** 29只指数的数据状态、收益变化和风险调整后表现。
3. **重点个案：** 4只指数的资产选择、发行材料、走势与证据边界。
4. **机制分析：** 多资产策略的过拟合来源与替代解释。
5. **研究评价：** 原文发现的可复现性、结论边界与待补证据。

> 叙事顺序：指数筛选 → 全景比较 → 重点个案 → 机制解释 → 研究评价。
""",
        """# [背景1] 指数筛选与方法论

**公众号原文的筛选逻辑**

1. 在Wind指数库检索“全天候”“资产配置”“大类资产配置”“多资产”“风险平价”等关键词；
2. 逐只核查底层资产，要求至少覆盖股票、债券、商品、另类中的两个大类；
3. 排除纯权益、纯固收、纯另类或行业主题指数，以及非策略型基金基准指数；
4. 按基日与发布日期切分“样本内”和“样本外”，最终得到29只指数：19只可比较发布前后，3只仅有公开运行记录，7只停更或数据不足。

**本研究如何使用这29只指数**

- 不重新构造样本池，直接以公众号原文筛出的29只指数作为研究母样本；
- 使用Wind补充基本信息和实际更新日行情，并按统一公式复算收益、波动、回撤和夏普；
- 切分日期沿用原文，但将“样本内/样本外”严谨表述为“发布前回溯期/发布后运行期”；
- 先比较29只指数的整体分布，再对4只重点指数分析资产选择、运行表现和证据边界。

> **一句话概括：** 本文按原文保留29只指数：CALLW有Wind行情并正常计算，CALLWE确认为停更且无数据，作为独立样本保留但不计算绩效。
""",
        f"""<!-- _class: universe -->
# [背景2] 29只券商多资产配置指数研究样本

{_universe_markdown_table(metrics)}

> 29只构成研究母样本；下一页再按19/3/7结构及统一复算结果展开。
""",
        f"""# [背景3] 29只样本结构与统一复算结果

{_image_markdown(image[FIGURE_NAMES[0]], 720)}

- **构造方式：** 左图合并原文19/3/7分组与Wind行情覆盖；右图只统计原文比较组中可统一复算的{len(formal)}只指数。
- **代码核对：** CALLW.WI为高华中国全天候，拥有完整行情并进入正式比较；CALLWE.WI按原文作为另一只指数保留，并确认停更且无数据，未使用CALLW行情替代。
- **可复算补充：** GT01.WI已用Wind单独导出的2015-01-05起完整日行情补齐；原文19只比较组现已19/19全部可按统一口径复算。
- **读图：** 29只中{prices}只有行情，19只原文比较组中有{len(formal)}只可复算；其中{overfit}只收益衰减超过2个百分点。
- **含义：** 后续发布前后比较以这{len(formal)}只为统计范围，其他指数保留在全景表中，但不混入同一结论。

> **研究评价：** 收益衰减并非个别现象，与原文判断方向一致；但这一分布只能提出过拟合担忧，不能直接完成因果归因。
""",
        f"""# [全景1] 发布后收益与夏普的联合变化

{_image_markdown(image[FIGURE_NAMES[1]], 760)}

- **构造方式：** 两个面板使用完全相同的指数顺序；空心点为发布前、实心点为发布后，红色箭头表示数值上升，绿色表示数值下降。
- **核心分布：** {len(joint)}只中{both_deteriorated}只（{both_deteriorated / len(joint):.0%}）收益和夏普同时下降，{both_improved}只（{both_improved / len(joint):.0%}）同时改善，{mixed_direction}只（{mixed_direction / len(joint):.0%}）方向不一致；收益衰减超过2个百分点的{overfit}只指数中，夏普{overfit_sharpe_down}/{overfit}同步下降。
- **高夏普检验：** 发布前夏普与后续收益衰减的Pearson相关为{pearson_correlation:.2f}，但Spearman秩相关仅{spearman_correlation:.2f}，剔除CI011800后Pearson相关降至{leave_one_out_correlation:.2f}。

> **统计结论：** 发布后弱化不只表现为收益降低，也伴随风险调整后表现走弱；但夏普以收益为分子，两者不是独立证据。“越完美越翻车”可作风险提示，不能写成无例外的统计规律。
""",
        f"""# [全景2] 收益衰减前十的多维诊断

{_image_markdown(image[FIGURE_NAMES[2]], 720)}

- **构造方式：** 收益和夏普按“发布后−发布前”计算；波动改善按“发布前波动−发布后波动”计算；最大回撤改善按“发布前回撤幅度−发布后回撤幅度”计算。
- **颜色规则：** 四列全部统一为正值表示改善、负值表示变差；红色=变好，绿色=变差。
- **衰减幅度：** 前十只的年化收益平均下降{top_decay_mean * 100:.1f}个百分点，中位数为{top_decay_median * 100:.1f}个百分点，四分位区间为{top_decay_q25 * 100:.1f}—{top_decay_q75 * 100:.1f}个百分点；其中{top_over_five}只衰减超过5个百分点。
- **风险共振：** 前十只的夏普全部下降，平均下降{top_sharpe_mean:.2f}、中位数下降{top_sharpe_median:.2f}；{top_mdd_worse}只最大回撤扩大，{top_vol_worse}只波动率上升，{top_joint_risk_worse}只同时出现波动上升和回撤扩大。
- **样本强弱：** 前十只中{len(top_decay) - len(top_short)}只已有一年以上发布后记录；{top_short_text}不足一年，排名仍可能被短期行情和年化处理放大。

> **统计结论：** 前十样本呈现集中且多维的发布后恶化，并非只由一两只极端指数驱动；但前十本就按收益衰减筛选，真正增加信息的是夏普、回撤、波动和样本长度是否同步恶化，仍不能仅凭排名确认过拟合因果。
""",
        f"""# [复现] 原文口径与统一日频复算

{_image_markdown(image[FIGURE_NAMES[3]], 760)}

- **原文口径：** 原文注明日频夏普按√252、月频按√12年化；四只重点指数中CICSF040使用月频，其他三只未标为月频。
- **统一复算：** 为与原文同期对照，本研究统一截止到2026-08-05，全部使用Wind实际更新日、252年化和年化无风险利率1.5%；原文值不进入统一横向排名。
- **读图：** 收益差异相对有限，夏普差异更明显，尤其是GALLW发布前3.90与统一复算1.52。
- **无法确认：** 文章没有说明为什么CICSF040改用月频；可能与数据可得性有关，但现有材料不足以验证。

> **口径纠正：** 月频和日频的年化因子本身都常见，但混频估计受自相关和平滑影响，不能直接横比；已经年化的月频夏普也不应再二次“换算成日频夏普”。
""",
        f"""<!-- _class: focus -->
# [重点总览] 四只重点指数的证据结构

{_image_markdown(image[FIGURE_NAMES[4]], 650)}

{_focus_markdown_table(metrics)}

> **读图：** 各指数以自身起点归一为100，空心点为发布切分锚点；曲线终点高度同时受历史长度影响，不能直接视为策略优劣。
""",
        _case_slide(1, "CI011800.WI", metrics, evidence, image[FIGURE_NAMES[5]]),
        _case_slide(2, "CICSF040.WI", metrics, evidence, image[FIGURE_NAMES[6]]),
        _case_slide(3, "CI011001.WI", metrics, evidence, image[FIGURE_NAMES[7]]),
        _case_slide(4, "GALLW.WI", metrics, evidence, image[FIGURE_NAMES[8]]),
        """# [原因] 多资产策略的过拟合机制

| 机制 | 多资产策略中的表现 | 应补充的检验 |
| --- | --- | --- |
| 设计自由度高 | 资产池、风险预算、回看窗口、调仓频率、权重上下限均可调整 | 披露参数搜索范围、候选版本和冻结日期 |
| 历史选择偏差 | 只展示表现最好的版本，回溯曲线可能经历反复筛选 | 使用真正留出期、滚动走样和多重检验修正 |
| 市场环境变化 | 股债相关性、通胀、波动结构改变，旧参数未必适用 | 做市场状态分层和压力窗口分析 |
| 真实投资摩擦 | 费用、滑点、跟踪误差、QDII额度可能吞噬指数收益 | 用产品净值验证可复制性 |

- **原文判断的合理之处：** 越平滑、夏普越高、回撤越低的回测，越应该接受严格追问。
- **需要修正的：** “发布后变差”还可能来自市场环境、短样本、规则变化和数据版本。

> **结论边界：** 当前证据只能说“与过拟合担忧一致”，不能说“已经证明过拟合”。
""",
        f"""# [稳健性检验] 收益衰减结论的阈值与样本敏感性

{_image_markdown(image[FIGURE_NAMES[9]], 720)}

- **2个百分点阈值：** 全部可比样本为{overfit}/{len(formal)}；剔除发布后不足1年的指数后为{long_overfit}/{len(long_sample)}（{long_overfit / len(long_sample):.0%}）。
- **更严格阈值：** 当阈值提高到5个百分点时，分别只剩{high_threshold_all}/{len(formal)}和{high_threshold_long}/{len(long_sample)}。
- **分布位置：** {len(formal)}只指数的收益衰减中位数为{_pct(median_decay)}，说明整体方向仍偏向衰减，但“超过一半”的比例依赖阈值与短样本处理。

> **替换理由：** 原图Pearson r={pearson_correlation:.2f}，不能称为“没有相关性”；但剔除CI011800后r降至{leave_one_out_correlation:.2f}，Spearman仅{spearman_correlation:.2f}，且两变量共享收益成分。因此改用阈值与样本敏感性，直接检验原文“10/19”的稳健程度。
""",
        f"""# [结论] 收益衰减现象获得支持，过拟合归因仍需审慎

| 可以保留 | 需要修正 | 仍待确认 |
| --- | --- | --- |
| 29只筛选框架与全景比较有价值 | 发布前回溯期不等于严格训练集 | 四只指数的完整方法书与规则版本 |
| {overfit}/{len(formal)}只出现>2个百分点收益衰减 | 发布后变差不等于确认过拟合 | 历史成分、权重和资产收益贡献 |
| 高夏普和低回撤应触发更严格审查 | 短样本与不同收益类型需单独处理 | 产品净值、费用和实际跟踪误差 |
| 四只个案呈现出不同证据属性 | 指数收益不能表述为客户净收益 | 规则修订和历史回溯修订记录 |

**最终表述：** 同口径复算支持“收益衰减并非个别现象”；该现象与过拟合担忧一致，但现有证据不足以把全部衰减统一归因于过拟合。

> 下一步最有价值的补数不是继续增加收益图，而是取得方法书、历史权重和真实产品净值。
""",
    ]
    for page, index_values in enumerate(np.array_split(np.arange(len(metrics)), 3), start=1):
        chunk = metrics.iloc[index_values].copy()
        slides.append(
            f"""<!-- _class: appendix -->
# [附录] 29只指数统一指标表（{page}/3）

{_appendix_markdown_table(chunk)}

> 前/后=发布前回溯期/发布后运行期；—=无可复算区间；收益差=前收益−后收益。特殊组的补充复算不进入原文19只统计。
"""
        )
    markdown = header + "\n---\n".join(slides) + "\n"
    validate_slide_titles(markdown)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(markdown, encoding="utf-8")
    linked = validate_markdown_links(markdown, REPORT)
    if len(linked) != 10:
        raise AssertionError(f"Markdown应引用10张图，实际{len(linked)}张")
    if len(slides) != 19:
        raise AssertionError(f"Markdown页面数应为19，实际{len(slides)}")
    return REPORT


def main() -> None:
    books = load_source_workbook()
    cleaned, audit = clean_index_daily(books["Index_Daily"], CUTOFF)
    series_by_code = build_price_series(cleaned)
    metrics = calculate_universe_metrics(books["Index_Info"], series_by_code, audit)
    evidence = build_evidence_matrix(books, metrics)
    csv_paths = export_results(books, audit, metrics, evidence)
    image_paths = generate_all_figures(books, metrics, series_by_code, evidence)
    report_path = render_markdown_deck(metrics, evidence, image_paths)
    print(f"完成：{len(metrics)}只指数，{len(series_by_code)}只有行情，{len(csv_paths)}张CSV，{len(image_paths)}张图片")
    print(f"Markdown：{report_path}")


if __name__ == "__main__":
    main()
