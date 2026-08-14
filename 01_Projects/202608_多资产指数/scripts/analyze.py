"""Rebuild the evidence tables and figures for the four-index review.

Run from the project root with:

    MPLBACKEND=Agg MPLCONFIGDIR=.matplotlib \
        /Users/lizhexi/Desktop/LZX-Intern/.venv/bin/python scripts/analyze.py

The script never modifies the two source workbooks.  All output is written to
``results`` and ``figures`` and can be regenerated from scratch.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from metrics import (
    annual_returns,
    best_year_counterfactual,
    clean_prices,
    closest_candidate,
    maximum_drawdown,
    moving_block_bootstrap_return_delta,
    performance_metrics,
    return_method_candidates,
    rolling_metrics,
    sharpe_method_candidates,
    split_at_publication,
    stress_window_metrics,
    summarize_rolling_metric,
    volatility_method_candidates,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = ROOT / "四大类资产配置指数_原始数据.xlsx"
HAND_FILE = ROOT / "指数后复权收盘价.xlsx"
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
CUTOFF = pd.Timestamp("2026-08-11")
RISK_FREE_RATE = 0.015
PINGFANG_COLLECTION = Path(
    "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/"
    "86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc"
)
PINGFANG_SC_REGULAR = ROOT / ".matplotlib" / "fonts" / "PingFangSC-Regular.ttf"

CHART_SPECS = {
    "index_history": ("4只指数全历史走势比较", "01_全历史走势.png"),
    "pre_post": ("4只指数发布前后表现比较", "02_发布前后比较.png"),
    "annual_heatmap": ("4只指数年度收益比较", "03_年度收益比较.png"),
    "drawdowns": ("4只指数回撤路径比较", "04_回撤路径比较.png"),
    "rolling_sharpe": ("4只指数滚动夏普比较", "05_滚动夏普比较.png"),
    "common_interval": ("4只指数共同区间比较", "06_共同区间比较.png"),
    "article_audit": ("公众号统一口径复算", "07_公众号指标复算.png"),
    "constituents": ("CI011800成分变化", "08_CI011800成分变化.png"),
    "stress": ("4只指数压力窗口比较", "09_压力窗口比较.png"),
    "bootstrap": ("4只指数样本前后差异", "10_样本前后差异.png"),
    "annual_concentration": ("4只指数年度收益集中度", "11_年度收益集中度.png"),
    "article_sensitivity": ("公众号指标口径敏感性", "12_指标口径敏感性.png"),
}

INDIVIDUAL_CHART_SPECS = {
    "CI011800.WI": "13_CI011800个案走势.png",
    "CICSF040.WI": "14_CICSF040个案走势.png",
    "CI011001.WI": "15_CI011001个案走势.png",
    "GALLW.WI": "16_GALLW个案走势.png",
}

ORDER = ["CI011800.WI", "CICSF040.WI", "CI011001.WI", "GALLW.WI"]
NAMES = {
    "CI011800.WI": "国泰海通资产配置",
    "CICSF040.WI": "中信期货大类资产配置",
    "CI011001.WI": "国泰海通全天候",
    "GALLW.WI": "银河全天候",
}
SHORT_NAMES = {
    "CI011800.WI": "国泰海通资配",
    "CICSF040.WI": "中信期货",
    "CI011001.WI": "国泰海通全天候",
    "GALLW.WI": "银河全天候",
}
COLORS = {
    "CI011800.WI": "#C9485B",
    "CICSF040.WI": "#286983",
    "CI011001.WI": "#D9922E",
    "GALLW.WI": "#6E5AA8",
}

ARTICLE_CLAIMS = [
    ("CI011800.WI", "发布前回溯期", "annual_return", 0.0336, "年化收益"),
    ("CI011800.WI", "发布前回溯期", "max_drawdown", -0.0993, "最大回撤"),
    ("CI011800.WI", "发布前回溯期", "sharpe", 0.25, "夏普"),
    ("CI011800.WI", "发布后运行期", "annual_return", 0.1932, "年化收益"),
    ("CI011800.WI", "发布后运行期", "max_drawdown", -0.1029, "最大回撤"),
    ("CI011800.WI", "发布后运行期", "sharpe", 1.58, "夏普"),
    ("CICSF040.WI", "全历史", "annual_return", 0.1141, "年化收益"),
    ("CICSF040.WI", "全历史", "max_drawdown", -0.0385, "最大回撤"),
    ("CICSF040.WI", "全历史", "annual_volatility", 0.0469, "年化波动"),
    ("CICSF040.WI", "全历史", "sharpe", 2.08, "夏普"),
    ("CI011001.WI", "发布前回溯期", "annual_return", 0.0680, "年化收益"),
    ("CI011001.WI", "发布前回溯期", "max_drawdown", -0.0462, "最大回撤"),
    ("CI011001.WI", "发布前回溯期", "sharpe", 1.56, "夏普"),
    ("CI011001.WI", "发布后运行期", "annual_return", 0.0949, "年化收益"),
    ("CI011001.WI", "发布后运行期", "max_drawdown", -0.0304, "最大回撤"),
    ("CI011001.WI", "发布后运行期", "sharpe", 1.95, "夏普"),
    ("GALLW.WI", "发布前回溯期", "annual_return", 0.1238, "年化收益"),
    ("GALLW.WI", "发布前回溯期", "max_drawdown", -0.0544, "最大回撤"),
    ("GALLW.WI", "发布前回溯期", "sharpe", 3.90, "夏普"),
    ("GALLW.WI", "发布后运行期", "annual_return", 0.0864, "年化收益"),
    ("GALLW.WI", "发布后运行期", "max_drawdown", -0.0799, "最大回撤"),
    ("GALLW.WI", "发布后运行期", "sharpe", 1.61, "夏普"),
]


def select_simplified_chinese_font() -> tuple[str, Path]:
    """Extract and return Apple's Simplified Chinese PingFang face only."""
    if not PINGFANG_COLLECTION.exists():
        raise FileNotFoundError(f"未找到苹果苹方字体集合：{PINGFANG_COLLECTION}")
    if not PINGFANG_SC_REGULAR.exists():
        from fontTools.ttLib import TTCollection

        PINGFANG_SC_REGULAR.parent.mkdir(parents=True, exist_ok=True)
        collection = TTCollection(PINGFANG_COLLECTION)
        collection.fonts[3].save(PINGFANG_SC_REGULAR)
        collection.close()
    fm.fontManager.addfont(PINGFANG_SC_REGULAR)
    family = fm.FontProperties(fname=PINGFANG_SC_REGULAR).get_name()
    if family not in {"PingFang SC", "苹方-简"} or "HK" in family.upper():
        raise RuntimeError(f"加载的不是简体苹方字体：{family}")
    return family, PINGFANG_SC_REGULAR


def configure_charts() -> None:
    family, _ = select_simplified_chinese_font()
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [family],
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "#FBFAF7",
            "axes.edgecolor": "#A6A6A6",
            "axes.titleweight": "normal",
            "axes.titlesize": 15,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.frameon": False,
            "savefig.bbox": "tight",
            "savefig.dpi": 180,
        }
    )


def load_inputs() -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, pd.Series], dict[str, pd.Series]]:
    books = pd.read_excel(RAW_FILE, sheet_name=None)
    info = books["Index_Info"].copy()
    for column in ["发布日期", "基期", "提取日期"]:
        info[column] = pd.to_datetime(info[column], errors="coerce").dt.normalize()

    daily = books["Index_Daily"].copy()
    daily["日期"] = pd.to_datetime(daily["日期"]).dt.normalize()
    price_column = "最早交易日期到2026年8月11日每日收盘价"
    raw_series = {
        code: clean_prices(group.set_index("日期")[price_column].loc[:CUTOFF])
        for code, group in daily.groupby("Wind代码")
    }

    hand = pd.read_excel(HAND_FILE, sheet_name=0, header=1)
    hand = hand.rename(columns={hand.columns[0]: "日期"})
    hand["日期"] = pd.to_datetime(hand["日期"]).dt.normalize()
    hand_series: dict[str, pd.Series] = {}
    for column in hand.columns[1:]:
        code = str(column).split()[-1]
        values = pd.Series(hand[column].to_numpy(), index=hand["日期"])
        hand_series[code] = clean_prices(values.loc[:CUTOFF])
    return books, info, raw_series, hand_series


def save_csv(frame: pd.DataFrame, name: str, index: bool = False) -> None:
    frame.to_csv(RESULTS / name, index=index, encoding="utf-8-sig")


def audit_workbooks(
    books: dict[str, pd.DataFrame],
    raw_series: dict[str, pd.Series],
    hand_series: dict[str, pd.Series],
) -> pd.DataFrame:
    rows = []
    for code in ORDER:
        raw = raw_series[code]
        hand = hand_series[code]
        overlap = raw.index.intersection(hand.index)
        difference = (raw.loc[overlap] - hand.loc[overlap]).abs()
        extra_dates = hand.index.difference(raw.index)
        rows.append(
            {
                "指数代码": code,
                "指数简称": NAMES[code],
                "原始表观测数": len(raw),
                "原始表起始日": raw.index[0],
                "原始表截止日": raw.index[-1],
                "手工表正值观测数": len(hand),
                "手工表起始日": hand.index[0],
                "手工表截止日": hand.index[-1],
                "共同日期数": len(overlap),
                "手工表额外日期数": len(extra_dates),
                "共同日期最大绝对点位差": difference.max(),
                "共同日期平均绝对点位差": difference.mean(),
                "是否在两位小数舍入误差内": bool((difference <= 0.0051).all()),
            }
        )
    audit = pd.DataFrame(rows)
    constituents = books["Constituents_Weights"]
    maps = books["Underlying_Map"]
    addendum = pd.DataFrame(
        [
            {
                "检查项": "成分权重非空数",
                "结果": int(constituents["权重(%)"].notna().sum()),
                "解释": "权重全部缺失，不能做真实收益贡献或风险贡献",
            },
            {
                "检查项": "CI011800历史成分快照数",
                "结果": int(pd.to_datetime(constituents["快照日期"]).nunique()),
                "解释": "仅能观察成分名单变化和数量，不能还原组合",
            },
            {
                "检查项": "Underlying_Map记录数",
                "结果": int(len(maps)),
                "解释": "映射表与最新成分快照并非完全一致，不能视为完整最新持仓",
            },
        ]
    )
    save_csv(audit, "数据对账.csv")
    save_csv(addendum, "数据缺口审计.csv")
    return audit


def metric_row(code: str, period: str, series: pd.Series) -> dict[str, object]:
    zero = performance_metrics(series, annual_risk_free_rate=0.0)
    rf = performance_metrics(series, annual_risk_free_rate=RISK_FREE_RATE)
    fields: dict[str, object] = {
        "指数代码": code,
        "指数简称": NAMES[code],
        "区间": period,
    }
    fields.update(zero)
    fields["sharpe_daily_rf1.5"] = rf["sharpe_daily"]
    fields["sharpe_monthly_rf1.5"] = rf["sharpe_monthly"]
    return fields


def calculate_performance(
    info: pd.DataFrame,
    series_by_code: dict[str, pd.Series],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lookup = info.set_index("Wind代码")
    metric_rows: list[dict[str, object]] = []
    annual = {}
    rolling_parts = []
    bootstrap_rows = []
    for code in ORDER:
        series = series_by_code[code]
        publication = lookup.loc[code, "发布日期"]
        pre, post, anchor = split_at_publication(series, publication)
        metric_rows.append(metric_row(code, "全历史", series))
        if len(pre) >= 2:
            metric_rows.append(metric_row(code, "发布前回溯期", pre))
        metric_rows.append(metric_row(code, "发布后运行期", post))
        annual[SHORT_NAMES[code]] = annual_returns(series)

        roll = rolling_metrics(series, 252, RISK_FREE_RATE).reset_index(names="日期")
        roll.insert(0, "指数代码", code)
        rolling_parts.append(roll)

        if len(pre) >= 3 and len(post) >= 3:
            boot = moving_block_bootstrap_return_delta(
                pre.pct_change(fill_method=None).dropna(),
                post.pct_change(fill_method=None).dropna(),
                block_size=21,
                simulations=5000,
            )
            bootstrap_rows.append(
                {
                    "指数代码": code,
                    "指数简称": NAMES[code],
                    "发布切分锚点": anchor,
                    "发布前日收益数": len(pre) - 1,
                    "发布后日收益数": len(post) - 1,
                    **boot,
                    "说明": "21日移动区块bootstrap；仅衡量均值差不确定性，不是技能因果检验",
                }
            )

    common_start = max(series.index[0] for series in series_by_code.values())
    common_end = min(series.index[-1] for series in series_by_code.values())
    for code in ORDER:
        metric_rows.append(metric_row(code, "共同区间", series_by_code[code].loc[common_start:common_end]))

    metrics = pd.DataFrame(metric_rows)
    annual_frame = pd.DataFrame(annual).sort_index()
    rolling_frame = pd.concat(rolling_parts, ignore_index=True)
    bootstrap = pd.DataFrame(bootstrap_rows)
    save_csv(metrics, "统一绩效.csv")
    save_csv(annual_frame.reset_index(names="年份"), "年度收益.csv")
    save_csv(rolling_frame, "滚动252日指标.csv")
    save_csv(bootstrap, "发布前后bootstrap.csv")
    return metrics, annual_frame, rolling_frame, bootstrap


def calculate_rolling_summary(rolling: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for code in ORDER:
        part = rolling.loc[rolling["指数代码"] == code].set_index("日期")["rolling_sharpe"]
        rows.append({"指数代码": code, "指数简称": NAMES[code], **summarize_rolling_metric(part)})
    frame = pd.DataFrame(rows)
    save_csv(frame, "滚动指标摘要.csv")
    return frame


def calculate_annual_concentration(series_by_code: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for code in ORDER:
        rows.append({"指数代码": code, "指数简称": NAMES[code], **best_year_counterfactual(series_by_code[code])})
    frame = pd.DataFrame(rows)
    save_csv(frame, "年度收益集中度.csv")
    return frame


def calculate_stress(series_by_code: dict[str, pd.Series]) -> pd.DataFrame:
    windows = {
        "2015股市急跌": ("2015-06-12", "2015-09-15"),
        "2018风险资产熊市": ("2018-01-24", "2019-01-03"),
        "2020疫情冲击": ("2020-02-19", "2020-03-23"),
        "2022股债压力": ("2021-12-31", "2022-12-30"),
        "2025多资产行情": ("2024-12-31", "2025-12-31"),
    }
    rows = []
    for event, (start, end) in windows.items():
        for code in ORDER:
            result = stress_window_metrics(series_by_code[code], start, end)
            rows.append(
                {
                    "事件": event,
                    "指定起始日": start,
                    "指定结束日": end,
                    "指数代码": code,
                    "指数简称": NAMES[code],
                    "实际起始点": result["actual_start"],
                    "实际结束点": result["actual_end"],
                    "窗口观测数": result["observations"],
                    "区间收益": result["window_return"],
                    "窗口内最大回撤": result["window_max_drawdown"],
                    "窗口峰值日": result["window_peak_date"],
                    "窗口谷值日": result["window_trough_date"],
                }
            )
    frame = pd.DataFrame(rows)
    save_csv(frame, "压力窗口.csv")
    return frame


def build_periods(
    info: pd.DataFrame,
    series_by_code: dict[str, pd.Series],
) -> dict[tuple[str, str], pd.Series]:
    lookup = info.set_index("Wind代码")
    periods: dict[tuple[str, str], pd.Series] = {}
    for code in ORDER:
        series = series_by_code[code]
        pre, post, _ = split_at_publication(series, lookup.loc[code, "发布日期"])
        periods[(code, "全历史")] = series
        periods[(code, "发布前回溯期")] = pre
        periods[(code, "发布后运行期")] = post
    return periods


def calculate_article_sensitivity(
    info: pd.DataFrame,
    raw_series: dict[str, pd.Series],
    hand_series: dict[str, pd.Series],
) -> pd.DataFrame:
    raw_periods = build_periods(info, raw_series)
    hand_periods = build_periods(info, hand_series)
    rows = []
    for code, period, metric, claimed, label in ARTICLE_CLAIMS:
        candidates: dict[str, float] = {}
        for source_label, periods in [("Wind实际更新日", raw_periods), ("手工统一日历", hand_periods)]:
            series = periods[(code, period)]
            if metric == "annual_return":
                methods = return_method_candidates(series)
            elif metric == "sharpe":
                methods = sharpe_method_candidates(series)
            elif metric == "annual_volatility":
                methods = volatility_method_candidates(series)
            else:
                drawdown = maximum_drawdown(series)["max_drawdown"]
                methods = {"标准历史峰值法": drawdown}
            candidates.update({f"{source_label}|{name}": value for name, value in methods.items()})

        # CI011800 has a non-trading base date and published base point.  Add
        # this auditable sensitivity only; do not optimize arbitrary start dates.
        if code == "CI011800.WI" and period == "发布前回溯期" and metric == "annual_return":
            row = info.set_index("Wind代码").loc[code]
            base_augmented = pd.concat(
                [pd.Series([float(row["基点"])], index=[pd.Timestamp(row["基期"])]), raw_periods[(code, period)]]
            )
            for name, value in return_method_candidates(base_augmented).items():
                candidates[f"Wind基点敏感性|{name}"] = value

        closest = closest_candidate(candidates, claimed)
        scale = 1.0 if metric == "sharpe" else 100.0
        gap_display = closest["absolute_gap"] * scale
        if metric == "sharpe":
            status = "可解释" if gap_display <= 0.05 else "近似" if gap_display <= 0.20 else "未解释"
        else:
            status = "可解释" if gap_display <= 0.06 else "近似" if gap_display <= 0.50 else "未解释"
        rows.append(
            {
                "指数代码": code,
                "指数简称": NAMES[code],
                "区间": period,
                "指标": label,
                "原文数值": claimed,
                "最接近数值": closest["value"],
                "绝对差": closest["absolute_gap"],
                "最接近预定义口径": closest["method"],
                "判定": status,
                "候选方法数": len(candidates),
                "说明": "只枚举预先定义的两数据日历、频率、Rf与年化方法；未搜索任意起止日",
            }
        )
    frame = pd.DataFrame(rows)
    save_csv(frame, "公众号口径敏感性.csv")
    return frame


def calculate_article_common_method(
    info: pd.DataFrame,
    raw_series: dict[str, pd.Series],
    hand_series: dict[str, pd.Series],
) -> pd.DataFrame:
    """Rank single methods that must be applied consistently to all claims."""
    periods_by_source = {
        "Wind实际更新日": build_periods(info, raw_series),
        "手工统一日历": build_periods(info, hand_series),
    }
    claim_groups = {
        "年化收益": [claim for claim in ARTICLE_CLAIMS if claim[2] == "annual_return"],
        "夏普": [claim for claim in ARTICLE_CLAIMS if claim[2] == "sharpe"],
    }
    rows = []
    for metric_label, claims in claim_groups.items():
        generator = return_method_candidates if metric_label == "年化收益" else sharpe_method_candidates
        display_scale = 100.0 if metric_label == "年化收益" else 1.0
        display_unit = "百分点" if metric_label == "年化收益" else "夏普值"
        for source, periods in periods_by_source.items():
            method_names = generator(periods[(claims[0][0], claims[0][1])]).keys()
            for method in method_names:
                errors = []
                for code, period, _, claimed, _ in claims:
                    current = generator(periods[(code, period)])[method]
                    errors.append((current - claimed) * display_scale)
                error_array = np.asarray(errors, dtype=float)
                rows.append(
                    {
                        "指标组": metric_label,
                        "数据源": source,
                        "统一方法": method,
                        "声明数": len(errors),
                        "平均绝对误差": float(np.mean(np.abs(error_array))),
                        "均方根误差": float(np.sqrt(np.mean(error_array**2))),
                        "最大绝对误差": float(np.max(np.abs(error_array))),
                        "误差单位": display_unit,
                    }
                )
    frame = pd.DataFrame(rows).sort_values(["指标组", "平均绝对误差", "均方根误差"])
    frame["组内排名"] = frame.groupby("指标组").cumcount() + 1
    save_csv(frame, "公众号统一口径检验.csv")
    return frame


def calculate_constituent_turnover(books: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    constituents = books["Constituents_Weights"].copy()
    constituents["快照日期"] = pd.to_datetime(constituents["快照日期"]).dt.normalize()
    rows = []
    previous: set[str] | None = None
    for date, group in constituents.groupby("快照日期", sort=True):
        current = set(group["成分代码"].dropna())
        rows.append(
            {
                "快照日期": date,
                "成分数量": len(current),
                "新增数量": np.nan if previous is None else len(current - previous),
                "剔除数量": np.nan if previous is None else len(previous - current),
                "相邻快照Jaccard": np.nan
                if previous is None
                else len(current & previous) / len(current | previous),
            }
        )
        previous = current
    turnover = pd.DataFrame(rows)

    latest_date = constituents["快照日期"].max()
    latest = constituents.loc[constituents["快照日期"] == latest_date, ["成分代码", "成分简称"]]
    maps = books["Underlying_Map"].copy().rename(columns={"Wind代码": "成分代码"})
    latest_map = latest.merge(
        maps[["成分代码", "投资类型_一级分类", "投资类型_二级分类", "跟踪指数代码"]],
        how="left",
        on="成分代码",
    )
    latest_map.insert(0, "快照日期", latest_date)
    latest_map["映射状态"] = np.where(latest_map["投资类型_一级分类"].notna(), "已映射", "映射缺失")
    save_csv(turnover, "CI011800成分变动.csv")
    save_csv(latest_map, "CI011800最新成分映射.csv")
    return turnover, latest_map


def article_audit_field(metric: str) -> str:
    """Return the common comparison field used for each article metric."""
    return "sharpe_daily_rf1.5" if metric == "sharpe" else metric


def article_audit(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for code, period, metric, claimed, label in ARTICLE_CLAIMS:
        field = article_audit_field(metric)
        current = float(metrics.loc[(metrics["指数代码"] == code) & (metrics["区间"] == period), field].iloc[0])
        difference = current - claimed
        is_ratio = "sharpe" in field
        exact_tol = 0.05 if is_ratio else 0.0006
        near_tol = 0.20 if is_ratio else 0.005
        status = "可复现" if abs(difference) <= exact_tol else "近似" if abs(difference) <= near_tol else "不一致"
        rows.append(
            {
                "指数代码": code,
                "指数简称": NAMES[code],
                "区间": period,
                "指标": label,
                "原文数值": claimed,
                "统一口径复算": current,
                "差异": difference,
                "判定": status,
            }
        )
    frame = pd.DataFrame(rows)
    save_csv(frame, "公众号数字核验.csv")
    return frame


def add_source_note(ax: plt.Axes, note: str = "数据：Wind工作簿；计算：本项目脚本；截止：2026-08-11") -> None:
    ax.text(0, -0.16, note, transform=ax.transAxes, fontsize=8, color="#686868", va="top")


def publication_marker_position(
    normalized_prices: pd.Series,
    publication_date: pd.Timestamp,
) -> tuple[pd.Timestamp, float]:
    """Return the observable point used to mark an index publication date."""
    series = clean_prices(normalized_prices)
    candidates = series.loc[: pd.Timestamp(publication_date)]
    if candidates.empty:
        raise ValueError("Publication date precedes the available index history")
    marker_date = candidates.index[-1]
    return marker_date, float(candidates.iloc[-1])


def individual_period_bounds(
    dates: pd.DatetimeIndex,
    publication_date: pd.Timestamp,
) -> tuple[tuple[pd.Timestamp, pd.Timestamp] | None, tuple[pd.Timestamp, pd.Timestamp]]:
    """Return chart spans using the last observation not later than publication."""
    observed = pd.DatetimeIndex(dates).sort_values()
    candidates = observed[observed <= pd.Timestamp(publication_date)]
    if candidates.empty:
        raise ValueError("Publication date precedes the available index history")
    anchor = candidates[-1]
    pre = None if anchor == observed[0] else (observed[0], anchor)
    return pre, (anchor, observed[-1])


def individual_anomaly_summary(code: str, metrics: pd.DataFrame) -> str:
    """Build one factual, non-causal anomaly label from the metric table."""
    part = metrics[metrics["指数代码"] == code].set_index("区间")
    if code == "CI011800.WI":
        return "完整路径最大回撤-15.32%，高于分段回撤"
    if code == "CICSF040.WI":
        return "11.60年最大回撤仅-3.85%"
    pre = part.loc["发布前回溯期"]
    post = part.loc["发布后运行期"]
    if code == "CI011001.WI":
        delta = (post["annual_return"] - pre["annual_return"]) * 100
        return f"发布后年化仅提高{delta:.2f}个百分点"
    return f"发布后波动由{pre['annual_volatility']:.2%}升至{post['annual_volatility']:.2%}"


def individual_period_note(has_pre_period: bool) -> str:
    if not has_pre_period:
        return "本指数无发布前回溯段；浅色=发布后运行期；黑点=全历史最大回撤谷值；数据：Wind"
    return "灰色=发布前回溯期；浅色=发布后运行期；黑点=全历史最大回撤谷值；数据：Wind"


def plot_index_history(series_by_code: dict[str, pd.Series], info: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(12, 6.3))
    lookup = info.set_index("Wind代码")
    for code in ORDER:
        series = series_by_code[code]
        normalized = series / series.iloc[0] * 100
        ax.plot(normalized.index, normalized, lw=2, color=COLORS[code], label=SHORT_NAMES[code])
        pub = lookup.loc[code, "发布日期"]
        if pub <= series.index[-1]:
            marker_date, marker_value = publication_marker_position(normalized, pub)
            ax.scatter(
                marker_date,
                marker_value,
                s=105,
                facecolor="white",
                edgecolor=COLORS[code],
                linewidth=2.2,
                zorder=5,
            )
            offsets = {
                "CICSF040.WI": (10, 14),
                "CI011001.WI": (8, -20),
                "GALLW.WI": (8, 10),
                "CI011800.WI": (8, -20),
            }
            ax.annotate(
                f"发布 {pd.Timestamp(pub):%Y-%m-%d}",
                (marker_date, marker_value),
                xytext=offsets[code],
                textcoords="offset points",
                fontsize=7.5,
                color=COLORS[code],
                bbox={"boxstyle": "round,pad=0.18", "facecolor": "white", "edgecolor": "none", "alpha": 0.78},
                zorder=6,
            )
    ax.set_title(CHART_SPECS["index_history"][0])
    ax.set_ylabel("归一化指数点位")
    ax.grid(axis="y", color="#DEDDD8", lw=0.8)
    ax.legend(ncol=2, loc="upper left")
    add_source_note(ax, "空心圆之前为发布前回溯历史；CICSF040发布日=首个点位，标记与起点重合；数据：Wind；截止：2026-08-11")
    fig.savefig(FIGURES / CHART_SPECS["index_history"][1])
    plt.close(fig)


def plot_pre_post(metrics: pd.DataFrame) -> None:
    subset = metrics[metrics["区间"].isin(["发布前回溯期", "发布后运行期"])].copy()
    fig, ax = plt.subplots(figsize=(11, 6.2))
    markers = {"发布前回溯期": "o", "发布后运行期": "D"}
    for _, row in subset.iterrows():
        code = row["指数代码"]
        ax.scatter(
            abs(row["max_drawdown"]) * 100,
            row["annual_return"] * 100,
            s=105,
            marker=markers[row["区间"]],
            color=COLORS[code],
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )
        ax.annotate(
            SHORT_NAMES[code] + (" 前" if row["区间"] == "发布前回溯期" else " 后"),
            (abs(row["max_drawdown"]) * 100, row["annual_return"] * 100),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8.5,
        )
    ax.set_title(CHART_SPECS["pre_post"][0])
    ax.set_xlabel("最大回撤绝对值（%）→ 越右风险越大")
    ax.set_ylabel("几何年化收益（%）")
    ax.grid(color="#DEDDD8", lw=0.8)
    add_source_note(ax, "圆=发布前回溯期；菱形=发布后运行期；CICSF040因发布日期=基日，无独立发布前样本")
    fig.savefig(FIGURES / CHART_SPECS["pre_post"][1])
    plt.close(fig)


def plot_annual_heatmap(annual: pd.DataFrame) -> None:
    values = annual.T.to_numpy(float) * 100
    masked = np.ma.masked_invalid(values)
    limit = max(10, float(np.nanmax(np.abs(values))))
    fig, ax = plt.subplots(figsize=(13, 4.5))
    image = ax.imshow(masked, aspect="auto", cmap="RdYlGn", vmin=-limit, vmax=limit)
    ax.set_xticks(range(len(annual.index)), annual.index)
    ax.set_yticks(range(len(annual.columns)), annual.columns)
    ax.set_title(CHART_SPECS["annual_heatmap"][0])
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            if np.isfinite(values[i, j]):
                color = "white" if abs(values[i, j]) > limit * 0.55 else "#252525"
                ax.text(j, i, f"{values[i, j]:.1f}%", ha="center", va="center", fontsize=8, color=color)
    fig.colorbar(image, ax=ax, fraction=0.025, pad=0.02, label="年度收益（%）")
    add_source_note(ax, "年度收益以前年末点位为期初；首年以首个有效点位为期初")
    fig.savefig(FIGURES / CHART_SPECS["annual_heatmap"][1])
    plt.close(fig)


def plot_drawdowns(series_by_code: dict[str, pd.Series]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.2), sharex=False)
    for ax, code in zip(axes.flat, ORDER):
        series = series_by_code[code]
        drawdown = series / series.cummax() - 1
        ax.fill_between(drawdown.index, drawdown * 100, 0, color=COLORS[code], alpha=0.65)
        mdd = maximum_drawdown(series)
        ax.scatter(mdd["trough_date"], mdd["max_drawdown"] * 100, color="#222222", s=26, zorder=3)
        ax.set_title(f"{SHORT_NAMES[code]}  最大 {mdd['max_drawdown']:.1%}", fontsize=11)
        ax.grid(axis="y", color="#DEDDD8", lw=0.7)
        ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(xmax=100))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.suptitle(CHART_SPECS["drawdowns"][0], fontsize=16)
    fig.text(0.01, 0.005, "数据：Wind；计算：点位/历史峰值-1；截止：2026-08-11", fontsize=8, color="#686868")
    fig.tight_layout(rect=(0, 0.025, 1, 0.95))
    fig.savefig(FIGURES / CHART_SPECS["drawdowns"][1])
    plt.close(fig)


def plot_rolling_sharpe(rolling: pd.DataFrame, info: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.2), sharex=False, sharey=True)
    lookup = info.set_index("Wind代码")
    for ax, code in zip(axes.flat, ORDER):
        part = rolling[rolling["指数代码"] == code].set_index("日期")
        ax.plot(part.index, part["rolling_sharpe"], color=COLORS[code], lw=1.5)
        ax.axhline(0, color="#555555", lw=0.7)
        ax.axhline(1, color="#A9A9A9", lw=0.7, ls="--")
        pub = lookup.loc[code, "发布日期"]
        ax.axvline(pub, color="#222222", lw=0.9, ls=":")
        ax.set_title(SHORT_NAMES[code], fontsize=11)
        ax.grid(axis="y", color="#DEDDD8", lw=0.7)
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.suptitle(CHART_SPECS["rolling_sharpe"][0], fontsize=16)
    fig.text(0.01, 0.005, "虚线竖线=发布日期；日收益算术均值/样本标准差×√252；数据：Wind", fontsize=8, color="#686868")
    fig.tight_layout(rect=(0, 0.025, 1, 0.95))
    fig.savefig(FIGURES / CHART_SPECS["rolling_sharpe"][1])
    plt.close(fig)


def plot_common_interval(series_by_code: dict[str, pd.Series]) -> None:
    start = max(series.index[0] for series in series_by_code.values())
    end = min(series.index[-1] for series in series_by_code.values())
    fig, ax = plt.subplots(figsize=(12, 6.2))
    for code in ORDER:
        part = series_by_code[code].loc[start:end]
        normalized = part / part.iloc[0] * 100
        ax.plot(normalized.index, normalized, lw=2, color=COLORS[code], label=SHORT_NAMES[code])
    ax.set_title(CHART_SPECS["common_interval"][0])
    ax.set_ylabel("共同起点=100")
    ax.grid(axis="y", color="#DEDDD8", lw=0.8)
    ax.legend(ncol=2, loc="upper left")
    add_source_note(ax, f"共同区间：{start:%Y-%m-%d}至{end:%Y-%m-%d}；消除起始时间差，但仍未消除价格/全收益口径差异")
    fig.savefig(FIGURES / CHART_SPECS["common_interval"][1])
    plt.close(fig)


def plot_article_audit(audit: pd.DataFrame) -> None:
    focus = audit[audit["指标"].str.contains("年化收益|夏普")].copy()
    focus["标签"] = focus["指数代码"].map(SHORT_NAMES) + "\n" + focus["区间"].str.replace("期", "") + " " + np.where(focus["指标"].str.contains("夏普"), "夏普", "收益")
    # Express returns in percentage points; Sharpe stays as a ratio and is placed in a separate panel.
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8))
    for ax, is_sharpe, title in [(axes[0], False, "年化收益复算"), (axes[1], True, "夏普复算")]:
        part = focus[focus["指标"].str.contains("夏普") == is_sharpe].reset_index(drop=True)
        x = np.arange(len(part))
        old = part["原文数值"].to_numpy(float)
        new = part["统一口径复算"].to_numpy(float)
        if not is_sharpe:
            old, new = old * 100, new * 100
        ax.bar(x - 0.18, old, width=0.36, color="#B9B4AA", label="公众号原文（口径未知）")
        ax.bar(x + 0.18, new, width=0.36, color="#286983", label="统一口径复算")
        ax.set_xticks(x, part["标签"], rotation=35, ha="right")
        ax.set_title(title, fontsize=12)
        ax.grid(axis="y", color="#DEDDD8", lw=0.7)
        if not is_sharpe:
            ax.set_ylabel("%")
        ax.legend(fontsize=8)
    fig.suptitle(CHART_SPECS["article_audit"][0], fontsize=16)
    fig.text(
        0.01,
        0.005,
        "蓝柱统一口径：年化收益=实际日历CAGR；夏普=日频、√252、Rf=1.5%；灰柱为公众号原文，口径未知",
        fontsize=8,
        color="#686868",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    fig.savefig(FIGURES / CHART_SPECS["article_audit"][1])
    plt.close(fig)


def plot_constituents(turnover: pd.DataFrame) -> None:
    fig, ax1 = plt.subplots(figsize=(11.5, 5.8))
    ax1.plot(turnover["快照日期"], turnover["成分数量"], marker="o", lw=2, color=COLORS["CI011800.WI"])
    ax1.set_ylabel("成分数量")
    ax1.set_title(CHART_SPECS["constituents"][0])
    ax1.grid(axis="y", color="#DEDDD8", lw=0.8)
    ax2 = ax1.twinx()
    ax2.bar(turnover["快照日期"], turnover["相邻快照Jaccard"], width=35, color="#6F8B80", alpha=0.45)
    ax2.set_ylim(0, 1)
    ax2.set_ylabel("相邻快照Jaccard（越低更替越大）")
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    add_source_note(ax1, "成分名单来自Wind快照；权重字段0个非空，因此数量与名单变化不等同于换手率或资产暴露")
    fig.savefig(FIGURES / CHART_SPECS["constituents"][1])
    plt.close(fig)


def plot_stress(stress: pd.DataFrame) -> None:
    returns = stress.pivot(index="事件", columns="指数代码", values="区间收益").reindex(columns=ORDER)
    drawdowns = stress.pivot(index="事件", columns="指数代码", values="窗口内最大回撤").reindex(columns=ORDER)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6), sharey=True)
    for ax, pivot, title, colorbar_label in [
        (axes[0], returns, "窗口收益", "窗口收益（%）"),
        (axes[1], drawdowns, "窗口最大回撤", "窗口内最大回撤（%）"),
    ]:
        values = pivot.to_numpy(float) * 100
        masked = np.ma.masked_invalid(values)
        limit = max(5, float(np.nanmax(np.abs(values))))
        image = ax.imshow(masked, aspect="auto", cmap="RdYlGn", vmin=-limit, vmax=limit)
        ax.set_xticks(range(len(ORDER)), [SHORT_NAMES[c] for c in ORDER], rotation=25, ha="right")
        ax.set_yticks(range(len(pivot.index)), pivot.index)
        ax.set_title(title, fontsize=12)
        for i in range(values.shape[0]):
            for j in range(values.shape[1]):
                if np.isfinite(values[i, j]):
                    ax.text(j, i, f"{values[i, j]:.1f}%", ha="center", va="center", fontsize=8.5)
                else:
                    ax.text(j, i, "无样本", ha="center", va="center", fontsize=8, color="#777777")
        fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02, label=colorbar_label)
    fig.suptitle(CHART_SPECS["stress"][0], fontsize=16)
    fig.text(
        0.01,
        0.005,
        "窗口端点取不晚于指定日期的最近有效点位；回撤在实际窗口路径内计算；事件区间为研究者设定，并非指数官方状态定义",
        fontsize=8,
        color="#686868",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.94))
    fig.savefig(FIGURES / CHART_SPECS["stress"][1])
    plt.close(fig)


def plot_bootstrap(bootstrap: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10.5, 5.4))
    y = np.arange(len(bootstrap))
    mean = bootstrap["mean_delta"].to_numpy(float) * 100
    low = bootstrap["ci_low"].to_numpy(float) * 100
    high = bootstrap["ci_high"].to_numpy(float) * 100
    ax.errorbar(mean, y, xerr=[mean - low, high - mean], fmt="o", color="#286983", ecolor="#8BA2AC", capsize=5)
    ax.axvline(0, color="#333333", lw=0.9, ls="--")
    ax.set_yticks(y, bootstrap["指数代码"].map(SHORT_NAMES))
    ax.set_xlabel("发布后 - 发布前年化算术均值差（百分点）")
    ax.set_title(CHART_SPECS["bootstrap"][0])
    for i, probability in enumerate(bootstrap["probability_post_gt_pre"]):
        ax.text(high[i] + 0.3, i, f"P(后>前)={probability:.0%}", va="center", fontsize=8.5)
    ax.grid(axis="x", color="#DEDDD8", lw=0.8)
    add_source_note(ax, "21日移动区块bootstrap，5,000次；衡量样本不确定性，不识别市场环境或策略技能的因果效应")
    fig.savefig(FIGURES / CHART_SPECS["bootstrap"][1])
    plt.close(fig)


def plot_annual_concentration(concentration: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    x = np.arange(len(concentration))
    full = concentration["full_annual_return"].to_numpy(float) * 100
    without_best = concentration["counterfactual_annual_return"].to_numpy(float) * 100
    ax.bar(x - 0.2, full, width=0.4, color="#286983", label="全历史年化")
    ax.bar(x + 0.2, without_best, width=0.4, color="#B9B4AA", label="最佳年份收益设为0后的年化")
    ax.set_xticks(x, concentration["指数代码"].map(SHORT_NAMES))
    ax.set_ylabel("几何年化收益（%）")
    ax.set_title(CHART_SPECS["annual_concentration"][0])
    ax.grid(axis="y", color="#DEDDD8", lw=0.8)
    ax.legend()
    for i, row in concentration.reset_index(drop=True).iterrows():
        ax.text(i, max(full[i], without_best[i]) + 0.3, f"最佳：{int(row['best_year'])}  {row['best_year_return']:.1%}", ha="center", fontsize=8)
    add_source_note(ax, "将最佳日历年收益机械设为0并按原全期年数重算；仅衡量收益集中度，不是可交易策略")
    fig.savefig(FIGURES / CHART_SPECS["annual_concentration"][1])
    plt.close(fig)


def plot_article_sensitivity(sensitivity: pd.DataFrame) -> None:
    focus = sensitivity[sensitivity["指标"].isin(["年化收益", "夏普"])].copy()
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.8))
    for ax, metric, scale, title in [
        (axes[0], "年化收益", 100.0, "年化收益口径"),
        (axes[1], "夏普", 1.0, "夏普口径"),
    ]:
        part = focus[focus["指标"] == metric].copy()
        claimed = part["原文数值"].to_numpy(float) * scale
        closest = part["最接近数值"].to_numpy(float) * scale
        labels = part["指数代码"].map(SHORT_NAMES) + "\n" + part["区间"].str.replace("期", "")
        colors = [COLORS[code] for code in part["指数代码"]]
        ax.scatter(claimed, closest, s=75, c=colors, edgecolor="white", linewidth=0.8)
        bounds = [min(np.nanmin(claimed), np.nanmin(closest)), max(np.nanmax(claimed), np.nanmax(closest))]
        padding = max(0.1, (bounds[1] - bounds[0]) * 0.08)
        ax.plot([bounds[0] - padding, bounds[1] + padding], [bounds[0] - padding, bounds[1] + padding], ls="--", color="#777777")
        offsets = [(4, 4), (4, -18), (-70, 4), (4, 14), (-65, -18), (4, 4), (-70, 4)]
        for index, (x_value, y_value, label) in enumerate(zip(claimed, closest, labels)):
            offset = offsets[index % len(offsets)]
            ax.annotate(label, (x_value, y_value), xytext=offset, textcoords="offset points", fontsize=7.2)
        ax.set_xlabel("公众号原文" + ("（%）" if metric == "年化收益" else ""))
        ax.set_ylabel("最近可得值" + ("（%）" if metric == "年化收益" else ""))
        ax.set_title(title, fontsize=11.5)
        ax.grid(color="#DEDDD8", lw=0.7)
    fig.suptitle(CHART_SPECS["article_sensitivity"][0], fontsize=16)
    fig.text(
        0.01,
        0.005,
        "网格：Wind实际更新日/手工统一日历 × 常见年化方法 × 日周月频 × Rf 0%—3%；不搜索任意起止日；每个点可能对应不同公式",
        fontsize=8,
        color="#686868",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.94))
    fig.savefig(FIGURES / CHART_SPECS["article_sensitivity"][1])
    plt.close(fig)


def plot_individual_indices(
    series_by_code: dict[str, pd.Series],
    info: pd.DataFrame,
    metrics: pd.DataFrame,
) -> None:
    """Plot one publication-aware normalized history for each index."""
    lookup = info.set_index("Wind代码")
    for code in ORDER:
        series = series_by_code[code]
        normalized = series / series.iloc[0] * 100
        publication_date = lookup.loc[code, "发布日期"]
        pre_span, post_span = individual_period_bounds(normalized.index, publication_date)
        marker_date, marker_value = publication_marker_position(normalized, publication_date)
        drawdown = maximum_drawdown(series)

        fig, ax = plt.subplots(figsize=(11.8, 5.7))
        if pre_span is not None:
            ax.axvspan(*pre_span, color="#D9D6CF", alpha=0.34, label="发布前回溯期")
        ax.axvspan(*post_span, color=COLORS[code], alpha=0.09, label="发布后运行期")
        ax.plot(normalized.index, normalized, color=COLORS[code], lw=2.3)
        ax.scatter(
            marker_date,
            marker_value,
            s=105,
            facecolor="white",
            edgecolor=COLORS[code],
            linewidth=2.2,
            zorder=5,
        )
        ax.annotate(
            f"发布 {pd.Timestamp(publication_date):%Y-%m-%d}",
            (marker_date, marker_value),
            xytext=(8, 12),
            textcoords="offset points",
            fontsize=8.5,
            color=COLORS[code],
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.85},
        )
        trough_date = pd.Timestamp(drawdown["trough_date"])
        trough_value = float(normalized.loc[trough_date])
        ax.scatter(trough_date, trough_value, s=35, color="#222222", zorder=5)
        ax.annotate(
            f"全路径最大回撤 {drawdown['max_drawdown']:.2%}",
            (trough_date, trough_value),
            xytext=(8, -22),
            textcoords="offset points",
            fontsize=8.5,
            color="#333333",
        )
        ax.text(
            0.015,
            0.96,
            individual_anomaly_summary(code, metrics),
            transform=ax.transAxes,
            va="top",
            fontsize=10,
            color="#333333",
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#C8C4BC", "alpha": 0.9},
        )
        ax.set_title(f"{NAMES[code]}个案走势")
        ax.set_ylabel("首个点位=100")
        ax.grid(axis="y", color="#DEDDD8", lw=0.8)
        ax.legend(loc="lower right", ncol=2)
        add_source_note(ax, individual_period_note(pre_span is not None))
        fig.savefig(FIGURES / INDIVIDUAL_CHART_SPECS[code])
        plt.close(fig)


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    FIGURES.mkdir(exist_ok=True)
    configure_charts()
    books, info, raw_series, hand_series = load_inputs()
    audit_workbooks(books, raw_series, hand_series)
    metrics, annual, rolling, bootstrap = calculate_performance(info, raw_series)
    rolling_summary = calculate_rolling_summary(rolling)
    concentration = calculate_annual_concentration(raw_series)
    stress = calculate_stress(raw_series)
    turnover, _ = calculate_constituent_turnover(books)
    claims = article_audit(metrics)
    sensitivity = calculate_article_sensitivity(info, raw_series, hand_series)
    calculate_article_common_method(info, raw_series, hand_series)

    plot_index_history(raw_series, info)
    plot_pre_post(metrics)
    plot_annual_heatmap(annual)
    plot_drawdowns(raw_series)
    plot_rolling_sharpe(rolling, info)
    plot_common_interval(raw_series)
    plot_article_audit(claims)
    plot_constituents(turnover)
    plot_stress(stress)
    plot_bootstrap(bootstrap)
    plot_annual_concentration(concentration)
    plot_article_sensitivity(sensitivity)
    plot_individual_indices(raw_series, info, metrics)

    print(f"Wrote {len(list(RESULTS.glob('*.csv')))} CSV files and {len(list(FIGURES.glob('*.png')))} figures")


if __name__ == "__main__":
    main()
