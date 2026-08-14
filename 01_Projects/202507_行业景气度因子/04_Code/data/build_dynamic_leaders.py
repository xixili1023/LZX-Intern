#!/usr/bin/env python3
"""按日生成申万行业动态龙头股及连续等权捏合股。

评估使用截至当日的 90 个交易日；当日收盘后得到的名单从下一交易日
生效。大体量结果只写入仓库外的 InternData，并按月保存为 Parquet。
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


STOCK_ROOT = Path.home() / "Desktop/InternData/StockData/processed/uqer_equity_daily_hfq"
WEIGHT_ROOT = Path.home() / "Desktop/InternData/StockData/processed/uqer_sw_index_weights"
OUTPUT_ROOT = Path.home() / "Desktop/InternData/行业景气度项目Data/processed/dynamic_leaders"

EVALUATION_DAYS = 90
MIN_OBSERVATIONS = 81
HIGH_WEIGHT_THRESHOLD = 0.10
ROLLING_DAYS = 20
ROLLING_MIN_PERIODS = 18
MIN_ROLLING_WINDOWS = 57
ANNUALIZATION_DAYS = 252
WEIGHT_SUM_TOLERANCE = 0.001
MAX_MISSING_BENCHMARK_WEIGHT = 0.02


class DynamicLeaderError(RuntimeError):
    """输入数据或评价口径不满足要求。"""


def _ticker(series: pd.Series) -> pd.Series:
    return series.astype("string").str.replace(r"\.0$", "", regex=True).str.zfill(6)


def normalize_weight_units(weights: pd.DataFrame) -> pd.DataFrame:
    """将申万权重从百分数点转换为比例，并验证每个快照合计约为 1。"""
    result = weights.copy()
    result["effective_date"] = pd.to_datetime(result["effective_date"]).dt.normalize()
    result["index_ticker"] = result["index_ticker"].astype("string")
    result["constituent_ticker"] = _ticker(result["constituent_ticker"])
    result["weight"] = pd.to_numeric(result["weight"], errors="coerce")
    keys = ["effective_date", "index_ticker"]
    totals = result.groupby(keys, observed=True)["weight"].transform("sum")
    percent_mask = totals > 1.5
    result.loc[percent_mask, "weight"] = result.loc[percent_mask, "weight"] / 100.0
    totals = result.groupby(keys, observed=True)["weight"].sum()
    invalid = totals.loc[(totals - 1.0).abs() > WEIGHT_SUM_TOLERANCE]
    if not invalid.empty:
        sample = invalid.head(5).to_dict()
        raise DynamicLeaderError(f"行业权重快照合计不接近 1: {sample}")
    return result


def expand_weight_snapshots(weights: pd.DataFrame, trading_dates) -> pd.DataFrame:
    """将月度权重快照按已知信息向后生效为日频，不向过去回填。"""
    snapshots = normalize_weight_units(weights)
    dates = pd.DatetimeIndex(pd.to_datetime(trading_dates)).normalize().unique().sort_values()
    expanded = []
    for _, industry in snapshots.groupby("index_ticker", observed=True, sort=False):
        effective_dates = (
            industry[["effective_date"]].drop_duplicates().sort_values("effective_date")
        )
        calendar = pd.merge_asof(
            pd.DataFrame({"trade_date": dates}),
            effective_dates,
            left_on="trade_date",
            right_on="effective_date",
            direction="backward",
            allow_exact_matches=True,
        ).dropna(subset=["effective_date"])
        expanded.append(calendar.merge(industry, on="effective_date", how="inner"))
    result = pd.concat(expanded, ignore_index=True) if expanded else pd.DataFrame()
    return result.sort_values(
        ["trade_date", "index_ticker", "constituent_ticker"]
    ).reset_index(drop=True)


def prepare_stock_returns(stocks: pd.DataFrame) -> pd.DataFrame:
    """校验后复权价格并分别生成有效观测标记和评价收益。"""
    required = {"trade_date", "ticker", "close", "pre_close_hfq", "is_open"}
    missing = required - set(stocks.columns)
    if missing:
        raise DynamicLeaderError(f"股票行情缺少字段: {sorted(missing)}")
    result = stocks.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"]).dt.normalize()
    result["ticker"] = _ticker(result["ticker"])
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result["pre_close_hfq"] = pd.to_numeric(result["pre_close_hfq"], errors="coerce")
    price_valid = result["close"].gt(0) & result["pre_close_hfq"].gt(0)
    result["valid_observation"] = price_valid & result["is_open"].eq(1)
    result["stock_return"] = np.where(
        price_valid,
        result["close"] / result["pre_close_hfq"] - 1.0,
        np.nan,
    )
    # 有可靠价格的停牌日用于代表性评价时收益为 0，但不计入 obs_count。
    suspended = price_valid & ~result["is_open"].eq(1)
    result.loc[suspended, "stock_return"] = 0.0
    if result.duplicated(["trade_date", "ticker"]).any():
        raise DynamicLeaderError("股票行情存在 ticker + trade_date 重复主键")
    return result


def build_qualified_pool(
    stocks: pd.DataFrame,
    daily_weights: pd.DataFrame,
    industry_code: str,
    evaluation_date,
    window_dates,
) -> pd.DataFrame:
    """按固定 90 日分母计算当前行业成分的覆盖率和平均权重。"""
    dates = pd.DatetimeIndex(pd.to_datetime(window_dates)).normalize()
    if len(dates) != EVALUATION_DAYS:
        raise DynamicLeaderError(f"评价窗口必须恰好包含 {EVALUATION_DAYS} 个交易日")
    prepared = stocks if {"valid_observation", "stock_return"} <= set(stocks.columns) else prepare_stock_returns(stocks)
    date = pd.Timestamp(evaluation_date).normalize()
    industry_weights = daily_weights.loc[
        daily_weights["index_ticker"].astype(str).eq(str(industry_code))
        & daily_weights["trade_date"].isin(dates)
    ].copy()
    industry_weights["constituent_ticker"] = _ticker(industry_weights["constituent_ticker"])
    current = industry_weights.loc[
        industry_weights["trade_date"].eq(date) & industry_weights["weight"].gt(0),
        "constituent_ticker",
    ].drop_duplicates()
    if current.empty:
        return pd.DataFrame(columns=["ticker", "obs_ratio", "avg_weight_90", "te", "rho"])

    stock_window = prepared.loc[
        prepared["trade_date"].isin(dates) & prepared["ticker"].isin(current)
    ]
    obs = stock_window.groupby("ticker", observed=True)["valid_observation"].sum()
    first_seen = prepared.groupby("ticker", observed=True)["trade_date"].min()
    window_start = dates[0]
    old_enough = first_seen.reindex(current).le(window_start)

    average_weights = (
        industry_weights.loc[industry_weights["constituent_ticker"].isin(current)]
        .groupby("constituent_ticker", observed=True)["weight"]
        .sum()
        .div(EVALUATION_DAYS)
    )
    pool = pd.DataFrame({"ticker": current.astype("string").to_numpy()})
    pool["obs_ratio"] = pool["ticker"].map(obs).fillna(0).astype(float) / EVALUATION_DAYS
    pool["avg_weight_90"] = pool["ticker"].map(average_weights).fillna(0).astype(float)
    pool["listed_90_days"] = pool["ticker"].map(old_enough).fillna(False).astype(bool)
    pool = pool.loc[
        pool["obs_ratio"].ge(MIN_OBSERVATIONS / EVALUATION_DAYS)
        & pool["listed_90_days"]
    ].copy()
    pool["te"] = np.nan
    pool["rho"] = np.nan
    return pool.reset_index(drop=True)


def add_tracking_metrics(
    qualified: pd.DataFrame,
    prepared_stocks: pd.DataFrame,
    daily_weights: pd.DataFrame,
    industry_code: str,
    window_dates,
) -> pd.DataFrame:
    """计算剔除自身基准下的 20 日滚动 TE/相关系数中位数。"""
    dates = pd.DatetimeIndex(pd.to_datetime(window_dates)).normalize()
    industry_weights = daily_weights.loc[
        daily_weights["index_ticker"].astype(str).eq(str(industry_code))
    ].copy()
    weight_wide = industry_weights.pivot_table(
        index="trade_date", columns="constituent_ticker", values="weight", aggfunc="last"
    ).reindex(dates).fillna(0.0)
    return_wide = prepared_stocks.pivot_table(
        index="trade_date", columns="ticker", values="stock_return", aggfunc="last"
    ).reindex(dates)
    return _add_tracking_metrics_from_panels(
        qualified, return_wide, weight_wide
    )


def _add_tracking_metrics_from_panels(
    qualified: pd.DataFrame,
    return_wide: pd.DataFrame,
    weight_wide: pd.DataFrame,
) -> pd.DataFrame:
    result = qualified.copy()
    prior_weights = weight_wide.shift(1)

    for row_index, ticker in result["ticker"].items():
        stock_return = return_wide.get(
            ticker, pd.Series(index=return_wide.index, dtype=float)
        )
        other_weights = prior_weights.drop(columns=[ticker], errors="ignore")
        other_returns = return_wide.reindex(columns=other_weights.columns)
        total_other_weight = other_weights.sum(axis=1)
        available_weight = other_weights.where(other_returns.notna()).sum(axis=1)
        coverage = available_weight.div(total_other_weight.replace(0.0, np.nan))
        valid_day = coverage.ge(1.0 - MAX_MISSING_BENCHMARK_WEIGHT)
        benchmark = (other_weights * other_returns).sum(
            axis=1, min_count=1
        ).div(available_weight)
        benchmark = benchmark.where(valid_day)
        active = stock_return - benchmark
        te20 = active.rolling(ROLLING_DAYS, min_periods=ROLLING_MIN_PERIODS).std(ddof=1)
        te20 = te20 * np.sqrt(ANNUALIZATION_DAYS)
        rho20 = stock_return.rolling(
            ROLLING_DAYS, min_periods=ROLLING_MIN_PERIODS
        ).corr(benchmark)
        if te20.notna().sum() >= MIN_ROLLING_WINDOWS:
            result.loc[row_index, "te"] = float(te20.median())
        if rho20.notna().sum() >= MIN_ROLLING_WINDOWS:
            result.loc[row_index, "rho"] = float(rho20.median())
    return result


def _shadow_components(
    qualified: pd.DataFrame,
    industry_code: str,
    selection_date,
    effective_date,
) -> pd.DataFrame:
    """保存每天的 Top-3 等权影子组合，使合成净值跨状态连续。"""
    if len(qualified) < 3:
        return _empty_components()
    chosen = qualified.sort_values(
        ["avg_weight_90", "ticker"], ascending=[False, True]
    ).head(3)
    return pd.DataFrame(
        {
            "selection_date": pd.Timestamp(selection_date),
            "effective_date": effective_date,
            "industry_code": str(industry_code),
            "component_ticker": chosen["ticker"].to_numpy(),
            "component_rank": [1, 2, 3],
            "target_weight": [1 / 3] * 3,
            "avg_weight_90": chosen["avg_weight_90"].to_numpy(),
            "obs_ratio": chosen["obs_ratio"].to_numpy(),
        }
    )


def build_dynamic_leader_tables(
    stocks: pd.DataFrame,
    weights: pd.DataFrame,
    industry_codes: list[str] | None = None,
    evaluation_start=None,
    initial_nav: float | dict[str, float] = 100.0,
    initial_components: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """从已加载行情和权重构造三张日频结果表。"""
    prepared = prepare_stock_returns(stocks)
    trading_dates = pd.DatetimeIndex(
        prepared["trade_date"].drop_duplicates()
    ).sort_values()
    if len(trading_dates) < EVALUATION_DAYS:
        raise DynamicLeaderError("股票行情不足 90 个交易日")
    daily_weights = expand_weight_snapshots(weights, trading_dates)
    industries = sorted(daily_weights["index_ticker"].astype(str).unique())
    if industry_codes:
        requested = {str(code) for code in industry_codes}
        industries = [code for code in industries if code in requested]
    leaders_list = []
    components_list = []
    issues = []
    first_evaluation_position = EVALUATION_DAYS - 1
    if evaluation_start is not None:
        first_evaluation_position = max(
            first_evaluation_position,
            int(trading_dates.searchsorted(pd.Timestamp(evaluation_start).normalize())),
        )

    valid_wide = prepared.pivot(
        index="trade_date", columns="ticker", values="valid_observation"
    ).reindex(trading_dates).fillna(False)
    observation_count = valid_wide.rolling(
        EVALUATION_DAYS, min_periods=EVALUATION_DAYS
    ).sum()
    return_wide = prepared.pivot(
        index="trade_date", columns="ticker", values="stock_return"
    ).reindex(trading_dates)
    first_seen = prepared.groupby("ticker", observed=True)["trade_date"].min()

    for industry in industries:
        industry_daily = daily_weights.loc[
            daily_weights["index_ticker"].astype(str).eq(industry)
        ]
        weight_wide = industry_daily.pivot(
            index="trade_date", columns="constituent_ticker", values="weight"
        ).reindex(trading_dates).fillna(0.0)
        average_weight = weight_wide.rolling(
            EVALUATION_DAYS, min_periods=EVALUATION_DAYS
        ).mean()
        first_known_weight = pd.Timestamp(industry_daily["trade_date"].min())
        first_complete_weight_position = (
            int(trading_dates.searchsorted(first_known_weight))
            + EVALUATION_DAYS
            - 1
        )
        industry_start_position = max(
            first_evaluation_position, first_complete_weight_position
        )
        for position in range(industry_start_position, len(trading_dates)):
            date = trading_dates[position]
            current_weights = weight_wide.loc[date]
            current = current_weights.index[current_weights.gt(0)]
            if current.empty:
                continue
            window_start = trading_dates[position - EVALUATION_DAYS + 1]
            obs = observation_count.loc[date].reindex(current).fillna(0.0)
            old_enough = first_seen.reindex(current).le(window_start).fillna(False)
            eligible = current[(obs.ge(MIN_OBSERVATIONS) & old_enough).to_numpy()]
            qualified = pd.DataFrame(
                {
                    "ticker": eligible.astype("string"),
                    "obs_ratio": obs.reindex(eligible).to_numpy() / EVALUATION_DAYS,
                    "avg_weight_90": average_weight.loc[date]
                    .reindex(eligible)
                    .fillna(0.0)
                    .to_numpy(),
                    "listed_90_days": True,
                    "te": np.nan,
                    "rho": np.nan,
                }
            )
            if qualified.empty:
                issues.append(
                    {"trade_date": date, "industry_code": industry,
                     "issue": "NO_QUALIFIED_STOCK"}
                )
                continue
            high_count = qualified["avg_weight_90"].ge(HIGH_WEIGHT_THRESHOLD).sum()
            if high_count > 3:
                window_slice = slice(
                    position - EVALUATION_DAYS + 1, position + 1
                )
                qualified = _add_tracking_metrics_from_panels(
                    qualified,
                    return_wide.iloc[window_slice],
                    weight_wide.iloc[window_slice],
                )
            effective_date = (
                trading_dates[position + 1]
                if position + 1 < len(trading_dates) else pd.NaT
            )
            shadow = _shadow_components(
                qualified, industry, date, effective_date
            )
            if not shadow.empty:
                components_list.append(shadow)
            try:
                leaders, _ = select_leaders_for_industry(
                    qualified, industry, date, effective_date
                )
            except DynamicLeaderError as exc:
                issues.append(
                    {"trade_date": date, "industry_code": industry, "issue": str(exc)}
                )
                continue
            leaders_list.append(leaders)

    leader_pool = pd.concat(leaders_list, ignore_index=True) if leaders_list else pd.DataFrame()
    components = (
        pd.concat(components_list, ignore_index=True)
        if components_list else _empty_components()
    )
    nav_components = components
    if initial_components is not None and not initial_components.empty:
        nav_components = pd.concat(
            [initial_components, components], ignore_index=True
        )
    synthetic_nav = compute_synthetic_nav(
        prepared[["trade_date", "ticker", "stock_return"]],
        nav_components,
        initial_nav=initial_nav,
        start_date=evaluation_start,
    )
    return {
        "leader_pool_daily": leader_pool,
        "synthetic_nav_daily": synthetic_nav,
        "synthetic_components_daily": components,
        "quality_issues": pd.DataFrame(issues),
    }


def _empty_components() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "selection_date", "effective_date", "industry_code",
            "component_ticker", "component_rank", "target_weight",
            "avg_weight_90", "obs_ratio",
        ]
    )


def select_leaders_for_industry(
    qualified: pd.DataFrame,
    industry_code: str,
    evaluation_date,
    effective_date=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """应用 10% 分支规则，返回最终龙头和必要的捏合股成分。"""
    date = pd.Timestamp(evaluation_date).normalize()
    effective = (
        pd.NaT
        if effective_date is None or pd.isna(effective_date)
        else pd.Timestamp(effective_date).normalize()
    )
    q = qualified.copy()
    if q.empty:
        raise DynamicLeaderError(f"{industry_code} {date.date()} 没有合格股票")
    q["ticker"] = _ticker(q["ticker"])
    q = q.sort_values(["avg_weight_90", "ticker"], ascending=[False, True])
    high = q.loc[q["avg_weight_90"] >= HIGH_WEIGHT_THRESHOLD].copy()

    if high.empty:
        if len(q) < 3:
            raise DynamicLeaderError(
                f"{industry_code} {date.date()} 合格股票不足 3 只，无法构造 Top-3 捏合股"
            )
        chosen = q.head(3).copy()
        asset_id = f"SYNTH_SW_{industry_code}_{date:%Y%m%d}"
        leaders = pd.DataFrame(
            [{
                "trade_date": date,
                "effective_date": effective,
                "industry_code": str(industry_code),
                "asset_id": asset_id,
                "asset_type": "SYNTH",
                "stock_ticker": pd.NA,
                "selection_method": "SYNTH_TOP3_EQUAL",
                "selection_rank": 1,
                "score": np.nan,
                "te": np.nan,
                "rho": np.nan,
                "avg_weight_90": chosen["avg_weight_90"].sum(),
                "component_count": 3,
            }]
        )
        components = pd.DataFrame(
            {
                "selection_date": date,
                "effective_date": effective,
                "industry_code": str(industry_code),
                "component_ticker": chosen["ticker"].to_numpy(),
                "component_rank": [1, 2, 3],
                "target_weight": [1 / 3] * 3,
                "avg_weight_90": chosen["avg_weight_90"].to_numpy(),
                "obs_ratio": chosen["obs_ratio"].to_numpy(),
            }
        )
        return leaders, components

    if len(high) <= 3:
        selected = high.copy()
        selected["score"] = np.nan
        method = "WEIGHT_THRESHOLD_DIRECT"
    else:
        valid_te = q["te"].dropna()
        if valid_te.empty or high[["te", "rho"]].isna().any(axis=None):
            raise DynamicLeaderError(
                f"{industry_code} {date.date()} 的 TE/相关系数不足以完成评分"
            )
        te95 = float(valid_te.quantile(0.95))
        if te95 <= np.finfo(float).eps:
            high["te_comp"] = 1.0
        else:
            high["te_comp"] = (1.0 - high["te"] / te95).clip(0.0, 1.0)
        high["rho_comp"] = ((high["rho"] + 1.0) / 2.0).clip(0.0, 1.0)
        high["score"] = 0.60 * high["te_comp"] + 0.40 * high["rho_comp"]
        selected = high.sort_values(
            ["score", "avg_weight_90", "te", "ticker"],
            ascending=[False, False, True, True],
        ).head(3)
        method = "TE_CORR_SCORE"

    leaders = pd.DataFrame(
        {
            "trade_date": date,
            "effective_date": effective,
            "industry_code": str(industry_code),
            "asset_id": selected["ticker"].to_numpy(),
            "asset_type": "REAL",
            "stock_ticker": selected["ticker"].to_numpy(),
            "selection_method": method,
            "selection_rank": np.arange(1, len(selected) + 1),
            "score": selected["score"].to_numpy(),
            "te": selected.get("te", pd.Series(np.nan, index=selected.index)).to_numpy(),
            "rho": selected.get("rho", pd.Series(np.nan, index=selected.index)).to_numpy(),
            "avg_weight_90": selected["avg_weight_90"].to_numpy(),
            "component_count": 1,
        }
    )
    return leaders, _empty_components()


def compute_synthetic_nav(
    stock_returns: pd.DataFrame,
    selections: pd.DataFrame,
    initial_nav: float | dict[str, float] = 100.0,
    start_date=None,
) -> pd.DataFrame:
    """用 t-1 日确定的成分计算 t 日收益，并维持每行业连续净值。"""
    if selections.empty:
        return pd.DataFrame(
            columns=["trade_date", "industry_code", "synth_return_gross",
                     "synth_close_gross", "internal_turnover", "component_count"]
        )
    returns = stock_returns.copy()
    returns["trade_date"] = pd.to_datetime(returns["trade_date"]).dt.normalize()
    returns["ticker"] = returns["ticker"].astype("string")
    return_wide = returns.pivot(
        index="trade_date", columns="ticker", values="stock_return"
    ).sort_index()
    if start_date is not None:
        return_wide = return_wide.loc[
            return_wide.index >= pd.Timestamp(start_date).normalize()
        ]
    picks = selections.copy()
    picks["selection_date"] = pd.to_datetime(picks["selection_date"]).dt.normalize()
    picks["component_ticker"] = picks["component_ticker"].astype("string")
    dates = return_wide.index
    rows = []

    for industry, industry_picks in picks.groupby("industry_code", sort=True):
        nav = float(
            initial_nav.get(str(industry), 100.0)
            if isinstance(initial_nav, dict)
            else initial_nav
        )
        by_date = {
            date: dict(zip(group["component_ticker"], group["target_weight"]))
            for date, group in industry_picks.groupby("selection_date")
        }
        first_date = pd.Timestamp(dates[0])
        earlier_dates = [date for date in by_date if date < first_date]
        previous_target: dict[str, float] | None = (
            by_date[max(earlier_dates)] if earlier_dates else None
        )
        for date in dates:
            today_target = by_date.get(pd.Timestamp(date), previous_target)
            if previous_target is None and today_target is None:
                continue
            synth_return = np.nan
            if previous_target:
                day = return_wide.loc[date].rename("stock_return")
                values = pd.Series(
                    previous_target, dtype=float, name="weight"
                ).to_frame().join(day)
                if values["stock_return"].notna().all():
                    synth_return = float((values["weight"] * values["stock_return"]).sum())
                    nav *= 1.0 + synth_return
            turnover = np.nan
            if previous_target is not None and today_target is not None:
                names = set(previous_target) | set(today_target)
                turnover = 0.5 * sum(
                    abs(today_target.get(name, 0.0) - previous_target.get(name, 0.0))
                    for name in names
                )
            rows.append(
                {
                    "trade_date": pd.Timestamp(date),
                    "industry_code": str(industry),
                    "synth_return_gross": synth_return,
                    "synth_close_gross": nav,
                    "internal_turnover": turnover,
                    "component_count": len(previous_target) if previous_target else 0,
                }
            )
            previous_target = today_target
    return pd.DataFrame(rows)


def upsert_monthly_parquet(
    frame: pd.DataFrame,
    output_root: Path,
    date_column: str,
    primary_key: list[str],
    table_name: str | None = None,
    replace_existing_dates: bool = False,
    replace_month: bool = False,
) -> list[Path]:
    """按月合并主键、保留新记录，并原子替换受影响的 Parquet。"""
    if frame.empty:
        return []
    data = frame.copy()
    data[date_column] = pd.to_datetime(data[date_column]).dt.normalize()
    output_root = Path(output_root)
    written = []
    for period, new_month in data.groupby(data[date_column].dt.to_period("M"), sort=True):
        month_dir = output_root / f"year={period.year}" / f"month={period.month:02d}"
        target = month_dir / f"{period.year}{period.month:02d}.parquet"
        month_dir.mkdir(parents=True, exist_ok=True)
        if target.exists() and not replace_month:
            old_month = pd.read_parquet(target)
            if replace_existing_dates:
                scope = [date_column]
                if "industry_code" in new_month.columns:
                    scope.append("industry_code")
                replaced = new_month[scope].drop_duplicates().assign(_replace=True)
                old_month = old_month.merge(replaced, on=scope, how="left")
                old_month = old_month.loc[old_month["_replace"].isna()].drop(
                    columns="_replace"
                )
            combined = pd.concat([old_month, new_month], ignore_index=True)
        else:
            combined = new_month.copy()
        combined = combined.drop_duplicates(primary_key, keep="last").sort_values(primary_key)
        if table_name is not None:
            combined = coerce_output_schema(table_name, combined)
        handle, temporary_name = tempfile.mkstemp(prefix=f".{target.stem}-", suffix=".parquet", dir=month_dir)
        os.close(handle)
        temporary = Path(temporary_name)
        try:
            combined.to_parquet(temporary, index=False, compression="zstd")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        written.append(target)
    return written


def coerce_output_schema(table_name: str, frame: pd.DataFrame) -> pd.DataFrame:
    """固定跨月字段类型，尤其避免全空字符串列被 Arrow 写成 null。"""
    schemas = {
        "leader_pool_daily": {
            "dates": ["trade_date", "effective_date"],
            "strings": [
                "industry_code", "asset_id", "asset_type", "stock_ticker",
                "selection_method",
            ],
            "floats": ["score", "te", "rho", "avg_weight_90"],
            "ints": ["selection_rank", "component_count"],
        },
        "synthetic_nav_daily": {
            "dates": ["trade_date"],
            "strings": ["industry_code"],
            "floats": [
                "synth_return_gross", "synth_close_gross", "internal_turnover",
            ],
            "ints": ["component_count"],
        },
        "synthetic_components_daily": {
            "dates": ["selection_date", "effective_date"],
            "strings": ["industry_code", "component_ticker"],
            "floats": ["target_weight", "avg_weight_90", "obs_ratio"],
            "ints": ["component_rank"],
        },
    }
    result = frame.copy()
    schema = schemas[table_name]
    for column in schema["dates"]:
        result[column] = pd.to_datetime(result[column])
    for column in schema["strings"]:
        result[column] = result[column].astype("string")
    for column in schema["floats"]:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype("float64")
    for column in schema["ints"]:
        result[column] = pd.to_numeric(result[column], errors="raise").astype("int64")
    return result


def list_parquet_files(root: Path, end_date=None) -> list[Path]:
    """递归发现 Parquet；日行情可按 YYYYMMDD 文件名剪去结束日之后文件。"""
    root = Path(root)
    if not root.exists():
        raise DynamicLeaderError(f"输入目录不存在: {root}")
    files = sorted(root.rglob("*.parquet"))
    if end_date is not None:
        end_text = pd.Timestamp(end_date).strftime("%Y%m%d")
        files = [
            path
            for path in files
            if not (path.stem.isdigit() and len(path.stem) == 8)
            or path.stem <= end_text
        ]
    if not files:
        raise DynamicLeaderError(f"没有找到 Parquet 文件: {root}")
    return files


def _stock_file_dates(stock_root: Path, end_date=None) -> list[tuple[pd.Timestamp, Path]]:
    end = None if end_date is None else pd.Timestamp(end_date).normalize()
    dated_files = []
    for path in Path(stock_root).rglob("*.parquet"):
        if path.stem.isdigit() and len(path.stem) == 8:
            date = pd.to_datetime(path.stem, format="%Y%m%d")
            if end is None or date <= end:
                dated_files.append((date, path))
    return sorted(dated_files)


def _latest_output_date(output_root: Path) -> pd.Timestamp | None:
    files = sorted((Path(output_root) / "leader_pool_daily").rglob("*.parquet"))
    if not files:
        return None
    latest_file = files[-1]
    dates = pd.read_parquet(latest_file, columns=["trade_date"])["trade_date"]
    return pd.Timestamp(dates.max()).normalize()


def resolve_incremental_range(stock_root: Path, output_root: Path, end_date=None):
    """确定增量输出区间及其恰好 91 个交易日的输入预热起点。"""
    dated_files = _stock_file_dates(stock_root, end_date=end_date)
    if not dated_files:
        raise DynamicLeaderError(f"没有找到股票日行情: {stock_root}")
    stock_dates = pd.DatetimeIndex(date for date, _ in dated_files)
    last_output = _latest_output_date(output_root)
    if last_output is None:
        return {
            "input_start": stock_dates[0],
            "output_start": None,
            "end": stock_dates[-1],
            "last_output": None,
        }
    new_position = int(stock_dates.searchsorted(last_output, side="right"))
    if new_position >= len(stock_dates):
        return None
    input_position = max(0, new_position - EVALUATION_DAYS)
    return {
        "input_start": stock_dates[input_position],
        "output_start": stock_dates[new_position],
        "end": stock_dates[-1],
        "last_output": last_output,
    }


def load_incremental_state(
    output_root: Path,
    last_output_date,
    industry_codes: list[str] | None = None,
) -> tuple[dict[str, float], pd.DataFrame]:
    """读取增量首日所需的上一日合成净值和影子成分。"""
    date = pd.Timestamp(last_output_date).normalize()
    month_path = f"year={date.year}/month={date.month:02d}/{date:%Y%m}.parquet"
    nav_path = Path(output_root) / "synthetic_nav_daily" / month_path
    component_path = Path(output_root) / "synthetic_components_daily" / month_path
    if not nav_path.exists() or not component_path.exists():
        raise DynamicLeaderError("增量状态文件缺失，请使用 --full-rebuild")
    nav_frame = pd.read_parquet(
        nav_path,
        columns=["trade_date", "industry_code", "synth_close_gross"],
    )
    components = pd.read_parquet(component_path)
    nav_frame = nav_frame.loc[pd.to_datetime(nav_frame["trade_date"]).eq(date)]
    components = components.loc[
        pd.to_datetime(components["selection_date"]).eq(date)
    ]
    if industry_codes:
        requested = {str(code) for code in industry_codes}
        nav_frame = nav_frame.loc[nav_frame["industry_code"].astype(str).isin(requested)]
        components = components.loc[
            components["industry_code"].astype(str).isin(requested)
        ]
    nav = dict(
        zip(
            nav_frame["industry_code"].astype(str),
            nav_frame["synth_close_gross"].astype(float),
        )
    )
    if not nav or components.empty:
        raise DynamicLeaderError("上一日增量状态为空，请使用 --full-rebuild")
    return nav, components


def load_source_data(
    stock_root: Path = STOCK_ROOT,
    weight_root: Path = WEIGHT_ROOT,
    start_date=None,
    end_date=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按列投影读取行情和截至 end_date 已有的权重快照。"""
    if start_date is None:
        stock_files = list_parquet_files(stock_root, end_date=end_date)
    else:
        start = pd.Timestamp(start_date).normalize()
        stock_files = [
            path
            for date, path in _stock_file_dates(stock_root, end_date=end_date)
            if date >= start
        ]
        if not stock_files:
            raise DynamicLeaderError("指定增量区间没有股票行情文件")
    weight_files = list_parquet_files(weight_root)
    stocks = pd.read_parquet(
        stock_files,
        columns=["trade_date", "ticker", "close", "pre_close_hfq", "is_open"],
    )
    weights = pd.read_parquet(
        weight_files,
        columns=["index_ticker", "effective_date", "constituent_ticker", "weight"],
    )
    if end_date is not None:
        end = pd.Timestamp(end_date).normalize()
        stocks = stocks.loc[pd.to_datetime(stocks["trade_date"]).le(end)]
        weights = weights.loc[pd.to_datetime(weights["effective_date"]).le(end)]
    return stocks, weights


def save_dynamic_leader_tables(
    tables: dict[str, pd.DataFrame],
    output_root: Path = OUTPUT_ROOT,
    start_date=None,
    end_date=None,
    full_rebuild: bool = False,
) -> list[Path]:
    """将三张正式表按月增量写入固定目录。"""
    specs = {
        "leader_pool_daily": (
            "trade_date", ["trade_date", "industry_code", "asset_id"]
        ),
        "synthetic_nav_daily": (
            "trade_date", ["trade_date", "industry_code"]
        ),
        "synthetic_components_daily": (
            "selection_date",
            ["selection_date", "industry_code", "component_ticker"],
        ),
    }
    written = []
    for name, (date_column, primary_key) in specs.items():
        frame = tables[name].copy()
        if frame.empty:
            continue
        frame = coerce_output_schema(name, frame)
        dates = pd.to_datetime(frame[date_column])
        if start_date is not None:
            frame = frame.loc[dates.ge(pd.Timestamp(start_date).normalize())]
            dates = pd.to_datetime(frame[date_column])
        if end_date is not None:
            frame = frame.loc[dates.le(pd.Timestamp(end_date).normalize())]
        table_root = Path(output_root) / name
        table_written = upsert_monthly_parquet(
            frame,
            table_root,
            date_column=date_column,
            primary_key=primary_key,
            table_name=name,
            replace_existing_dates=True,
            replace_month=full_rebuild,
        )
        written.extend(table_written)
        if full_rebuild:
            expected = set(table_written)
            for stale_file in table_root.rglob("*.parquet"):
                if stale_file not in expected:
                    stale_file.unlink()
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成申万行业日频动态龙头股、连续捏合股净值和成分明细。"
    )
    parser.add_argument("--stock-root", type=Path, default=STOCK_ROOT)
    parser.add_argument("--weight-root", type=Path, default=WEIGHT_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--end-date", help="计算和输出结束日，默认使用全部已有数据。")
    parser.add_argument(
        "--full-rebuild",
        action="store_true",
        help="忽略已有结果并重算全部历史；默认只处理新增交易日。",
    )
    parser.add_argument(
        "--industry", nargs="+", help="可选，只计算指定申万行业代码。"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.full_rebuild:
        update_range = {
            "input_start": None,
            "output_start": None,
            "end": args.end_date,
            "last_output": None,
        }
        initial_nav = 100.0
        initial_components = None
    else:
        update_range = resolve_incremental_range(
            args.stock_root, args.output_root, end_date=args.end_date
        )
        if update_range is None:
            print("没有新增交易日，无需更新。")
            return
        if update_range["last_output"] is None:
            initial_nav = 100.0
            initial_components = None
        else:
            initial_nav, initial_components = load_incremental_state(
                args.output_root,
                update_range["last_output"],
                industry_codes=args.industry,
            )
    stocks, weights = load_source_data(
        args.stock_root,
        args.weight_root,
        start_date=update_range["input_start"],
        end_date=update_range["end"],
    )
    tables = build_dynamic_leader_tables(
        stocks,
        weights,
        industry_codes=args.industry,
        evaluation_start=update_range["output_start"],
        initial_nav=initial_nav,
        initial_components=initial_components,
    )
    written = save_dynamic_leader_tables(
        tables,
        output_root=args.output_root,
        start_date=update_range["output_start"],
        end_date=update_range["end"],
        full_rebuild=args.full_rebuild,
    )
    issues = tables["quality_issues"]
    print(
        f"完成：写入 {len(written)} 个月度文件；"
        f"龙头记录 {len(tables['leader_pool_daily']):,} 行；"
        f"质量异常 {len(issues):,} 条。"
    )


if __name__ == "__main__":
    main()
