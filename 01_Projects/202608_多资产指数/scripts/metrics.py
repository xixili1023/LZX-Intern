"""Transparent performance metrics for index-level price series.

The module deliberately separates index performance measurement from any
claim about investable portfolio performance.  It assumes positive index
levels on real observation dates and does not forward-fill missing dates.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

CALENDAR_DAYS_PER_YEAR = 365.2425
TRADING_DAYS_PER_YEAR = 252
MONTHS_PER_YEAR = 12


def clean_prices(prices: pd.Series) -> pd.Series:
    """Return a sorted, unique, positive price series."""
    series = pd.to_numeric(prices, errors="coerce").dropna()
    series.index = pd.to_datetime(series.index).normalize()
    series = series[~series.index.duplicated(keep="last")].sort_index()
    return series[series > 0].astype(float)


def calendar_years(start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Elapsed calendar years using the Gregorian mean year length."""
    days = (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds() / 86400
    return days / CALENDAR_DAYS_PER_YEAR


def maximum_drawdown(prices: pd.Series) -> dict[str, Any]:
    """Measure the deepest peak-to-trough loss and its recovery date."""
    series = clean_prices(prices)
    if series.empty:
        return {
            "max_drawdown": np.nan,
            "peak_date": pd.NaT,
            "trough_date": pd.NaT,
            "recovery_date": pd.NaT,
            "underwater_days": np.nan,
        }
    running_max = series.cummax()
    drawdown = series / running_max - 1
    trough_date = drawdown.idxmin()
    max_drawdown = float(drawdown.loc[trough_date])
    peak_date = series.loc[:trough_date].idxmax()
    later = series.loc[trough_date:]
    recovered = later[later >= series.loc[peak_date]]
    recovery_date = recovered.index[0] if not recovered.empty else pd.NaT
    end_date = recovery_date if pd.notna(recovery_date) else series.index[-1]
    return {
        "max_drawdown": max_drawdown,
        "peak_date": peak_date,
        "trough_date": trough_date,
        "recovery_date": recovery_date,
        "underwater_days": int((end_date - peak_date).days),
    }


def performance_metrics(
    prices: pd.Series,
    annual_risk_free_rate: float = 0.015,
) -> dict[str, Any]:
    """Calculate explicit daily and monthly performance statistics."""
    series = clean_prices(prices)
    if len(series) < 2:
        raise ValueError("At least two positive observations are required")

    years = calendar_years(series.index[0], series.index[-1])
    if years <= 0:
        raise ValueError("The series must span more than one calendar date")
    daily = series.pct_change().dropna()
    monthly_prices = series.resample("ME").last()
    monthly = monthly_prices.pct_change(fill_method=None).dropna()
    total_return = float(series.iloc[-1] / series.iloc[0] - 1)
    annual_return = float((series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1)
    annual_volatility = float(daily.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))

    daily_rf = (1 + annual_risk_free_rate) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    monthly_rf = (1 + annual_risk_free_rate) ** (1 / MONTHS_PER_YEAR) - 1
    sharpe_daily = (
        float((daily.mean() - daily_rf) / daily.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
        if daily.std(ddof=1) > 0
        else np.nan
    )
    sharpe_monthly = (
        float((monthly.mean() - monthly_rf) / monthly.std(ddof=1) * math.sqrt(MONTHS_PER_YEAR))
        if len(monthly) > 1 and monthly.std(ddof=1) > 0
        else np.nan
    )
    negative_daily = daily[daily < daily_rf] - daily_rf
    downside_deviation = (
        float(np.sqrt(np.mean(np.minimum(daily - daily_rf, 0) ** 2)) * math.sqrt(TRADING_DAYS_PER_YEAR))
        if len(daily)
        else np.nan
    )
    sortino = (
        float((daily.mean() - daily_rf) * TRADING_DAYS_PER_YEAR / downside_deviation)
        if downside_deviation > 0
        else np.nan
    )
    drawdown = maximum_drawdown(series)
    calmar = (
        float(annual_return / abs(drawdown["max_drawdown"]))
        if drawdown["max_drawdown"] < 0
        else np.nan
    )

    return {
        "start_date": series.index[0],
        "end_date": series.index[-1],
        "observations": int(len(series)),
        "years": years,
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe_daily": sharpe_daily,
        "sharpe_monthly": sharpe_monthly,
        "sortino_daily": sortino,
        "calmar": calmar,
        "positive_day_rate": float((daily > 0).mean()),
        "positive_month_rate": float((monthly > 0).mean()) if len(monthly) else np.nan,
        "best_day": float(daily.max()),
        "worst_day": float(daily.min()),
        **drawdown,
    }


def split_at_publication(
    prices: pd.Series,
    publication_date: pd.Timestamp,
) -> tuple[pd.Series, pd.Series, pd.Timestamp]:
    """Split at the last index point on/before publication.

    The anchor observation appears in both slices: it is the endpoint of the
    backfilled history and the starting capital for post-publication returns.
    """
    series = clean_prices(prices)
    candidates = series.index[series.index <= pd.Timestamp(publication_date)]
    if candidates.empty:
        raise ValueError("Publication date precedes the available index history")
    anchor = candidates[-1]
    return series.loc[:anchor], series.loc[anchor:], anchor


def rolling_metrics(
    prices: pd.Series,
    window: int = 252,
    annual_risk_free_rate: float = 0.015,
) -> pd.DataFrame:
    """Rolling one-year return, volatility, Sharpe and drawdown."""
    series = clean_prices(prices)
    returns = series.pct_change()
    rf = (1 + annual_risk_free_rate) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    out = pd.DataFrame(index=series.index)
    out["rolling_return"] = series / series.shift(window) - 1
    out["rolling_volatility"] = returns.rolling(window).std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)
    out["rolling_sharpe"] = (
        (returns.rolling(window).mean() - rf)
        / returns.rolling(window).std(ddof=1)
        * math.sqrt(TRADING_DAYS_PER_YEAR)
    )
    rolling_peak = series.rolling(window, min_periods=window).max()
    out["rolling_drawdown"] = series / rolling_peak - 1
    return out


def annual_returns(prices: pd.Series) -> pd.Series:
    """Calendar-year returns, using the prior year-end as each year's base."""
    series = clean_prices(prices)
    year_end = series.resample("YE").last()
    result = year_end.pct_change(fill_method=None)
    first_year = int(series.index[0].year)
    first_end = year_end.loc[year_end.index.year == first_year].iloc[0]
    result.loc[result.index.year == first_year] = first_end / series.iloc[0] - 1
    result.index = result.index.year
    return result


def stress_window_metrics(
    prices: pd.Series,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> dict[str, Any]:
    """Measure endpoint return and the deepest loss inside an event window.

    The actual endpoints are the latest valid observations no later than the
    requested dates.  This matches the event-window convention used in the
    report while retaining the full intra-window path for drawdown analysis.
    """
    series = clean_prices(prices)
    start_candidates = series.loc[: pd.Timestamp(start)]
    end_candidates = series.loc[: pd.Timestamp(end)]
    if start_candidates.empty or end_candidates.empty:
        return {
            "actual_start": pd.NaT,
            "actual_end": pd.NaT,
            "observations": 0,
            "window_return": np.nan,
            "window_max_drawdown": np.nan,
            "window_peak_date": pd.NaT,
            "window_trough_date": pd.NaT,
        }
    actual_start = start_candidates.index[-1]
    actual_end = end_candidates.index[-1]
    if actual_end <= actual_start:
        return {
            "actual_start": actual_start,
            "actual_end": actual_end,
            "observations": 0,
            "window_return": np.nan,
            "window_max_drawdown": np.nan,
            "window_peak_date": pd.NaT,
            "window_trough_date": pd.NaT,
        }
    window = series.loc[actual_start:actual_end]
    drawdown = maximum_drawdown(window)
    return {
        "actual_start": actual_start,
        "actual_end": actual_end,
        "observations": int(len(window)),
        "window_return": float(window.iloc[-1] / window.iloc[0] - 1),
        "window_max_drawdown": drawdown["max_drawdown"],
        "window_peak_date": drawdown["peak_date"],
        "window_trough_date": drawdown["trough_date"],
    }


def summarize_rolling_metric(values: pd.Series) -> dict[str, Any]:
    """Summarize a rolling metric without treating missing windows as zero."""
    series = pd.to_numeric(values, errors="coerce").dropna()
    if series.empty:
        return {
            "observations": 0,
            "minimum": np.nan,
            "minimum_date": pd.NaT,
            "maximum": np.nan,
            "maximum_date": pd.NaT,
            "latest": np.nan,
            "latest_date": pd.NaT,
            "share_above_zero": np.nan,
            "share_above_one": np.nan,
        }
    return {
        "observations": int(len(series)),
        "minimum": float(series.min()),
        "minimum_date": series.idxmin(),
        "maximum": float(series.max()),
        "maximum_date": series.idxmax(),
        "latest": float(series.iloc[-1]),
        "latest_date": series.index[-1],
        "share_above_zero": float((series > 0).mean()),
        "share_above_one": float((series > 1).mean()),
    }


def best_year_counterfactual(prices: pd.Series) -> dict[str, Any]:
    """Set the strongest calendar-year return to zero and re-annualize.

    This is a descriptive concentration check, not a claim that the best year
    could have been removed from an investable strategy in real time.
    """
    series = clean_prices(prices)
    yearly = annual_returns(series).dropna()
    if yearly.empty:
        raise ValueError("At least one calendar-year return is required")
    best_year = int(yearly.idxmax())
    best_return = float(yearly.loc[best_year])
    counterfactual = yearly.copy()
    counterfactual.loc[best_year] = 0.0
    counterfactual_total = float((1 + counterfactual).prod() - 1)
    years = calendar_years(series.index[0], series.index[-1])
    full_annual = float((series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1)
    counterfactual_annual = float((1 + counterfactual_total) ** (1 / years) - 1)
    return {
        "best_year": best_year,
        "best_year_return": best_return,
        "full_total_return": float(series.iloc[-1] / series.iloc[0] - 1),
        "full_annual_return": full_annual,
        "counterfactual_total_return": counterfactual_total,
        "counterfactual_annual_return": counterfactual_annual,
        "annual_return_drop": full_annual - counterfactual_annual,
    }


def return_method_candidates(prices: pd.Series) -> dict[str, float]:
    """Return a fixed grid of reasonable annual-return conventions."""
    series = clean_prices(prices)
    if len(series) < 2:
        raise ValueError("At least two observations are required")
    returns = series.pct_change(fill_method=None).dropna()
    log_returns = np.log(series).diff().dropna()
    years = calendar_years(series.index[0], series.index[-1])
    ratio = float(series.iloc[-1] / series.iloc[0])
    yearly = annual_returns(series).dropna()
    return {
        "实际日历CAGR": float(ratio ** (1 / years) - 1),
        "252交易日几何年化": float(ratio ** (TRADING_DAYS_PER_YEAR / len(returns)) - 1),
        "日收益算术均值×252": float(returns.mean() * TRADING_DAYS_PER_YEAR),
        "日对数收益指数化×252": float(np.exp(log_returns.mean() * TRADING_DAYS_PER_YEAR) - 1),
        "累计收益/实际年数": float((ratio - 1) / years),
        "完整年度收益算术均值": float(yearly.mean()) if len(yearly) else np.nan,
    }


def sharpe_method_candidates(
    prices: pd.Series,
    risk_free_rates: tuple[float, ...] = (0.0, 0.01, 0.015, 0.02, 0.025, 0.03),
) -> dict[str, float]:
    """Return an explicit frequency/risk-free-rate Sharpe grid.

    The grid is defined before comparison with article claims, avoiding
    arbitrary start-date or risk-free-rate tuning to manufacture a match.
    """
    series = clean_prices(prices)
    frequency_returns = {
        "日频": (series.pct_change(fill_method=None).dropna(), TRADING_DAYS_PER_YEAR),
        "周频": (series.resample("W-FRI").last().pct_change(fill_method=None).dropna(), 52),
        "月频": (series.resample("ME").last().pct_change(fill_method=None).dropna(), MONTHS_PER_YEAR),
    }
    result: dict[str, float] = {}
    for frequency, (returns, periods) in frequency_returns.items():
        standard_deviation = returns.std(ddof=1)
        for annual_rf in risk_free_rates:
            periodic_rf = (1 + annual_rf) ** (1 / periods) - 1
            label = f"{frequency}算术夏普|Rf={annual_rf:.1%}"
            result[label] = (
                float((returns.mean() - periodic_rf) / standard_deviation * math.sqrt(periods))
                if len(returns) > 1 and standard_deviation > 0
                else np.nan
            )
    daily = series.pct_change(fill_method=None).dropna()
    daily_volatility = daily.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)
    cagr = return_method_candidates(series)["实际日历CAGR"]
    for annual_rf in risk_free_rates:
        result[f"CAGR/日频波动|Rf={annual_rf:.1%}"] = (
            float((cagr - annual_rf) / daily_volatility) if daily_volatility > 0 else np.nan
        )
    return result


def volatility_method_candidates(prices: pd.Series) -> dict[str, float]:
    """Return common annualized volatility conventions."""
    series = clean_prices(prices)
    daily = series.pct_change(fill_method=None).dropna()
    weekly = series.resample("W-FRI").last().pct_change(fill_method=None).dropna()
    monthly = series.resample("ME").last().pct_change(fill_method=None).dropna()
    return {
        "日频标准差×√252": float(daily.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)),
        "周频标准差×√52": float(weekly.std(ddof=1) * math.sqrt(52)),
        "月频标准差×√12": float(monthly.std(ddof=1) * math.sqrt(MONTHS_PER_YEAR)),
    }


def closest_candidate(candidates: dict[str, float], target: float) -> dict[str, Any]:
    """Identify the nearest finite value in a predeclared method grid."""
    finite = [(name, float(value)) for name, value in candidates.items() if np.isfinite(value)]
    if not finite:
        return {"method": None, "value": np.nan, "absolute_gap": np.nan}
    name, value = min(finite, key=lambda item: abs(item[1] - target))
    return {"method": name, "value": value, "absolute_gap": abs(value - target)}


def _block_sample(values: np.ndarray, size: int, block_size: int, rng: np.random.Generator) -> np.ndarray:
    if len(values) == 0:
        raise ValueError("Bootstrap inputs cannot be empty")
    block_size = max(1, min(int(block_size), len(values)))
    starts = rng.integers(0, len(values) - block_size + 1, size=math.ceil(size / block_size))
    sampled = np.concatenate([values[start : start + block_size] for start in starts])
    return sampled[:size]


def moving_block_bootstrap_return_delta(
    pre_returns: pd.Series,
    post_returns: pd.Series,
    block_size: int = 21,
    simulations: int = 5000,
    seed: int = 20260812,
) -> dict[str, float]:
    """Bootstrap the post-minus-pre annualized arithmetic return difference.

    The procedure resamples contiguous daily-return blocks separately within
    each period, preserving short-run dependence without claiming a causal
    test of strategy skill.
    """
    pre = pd.to_numeric(pre_returns, errors="coerce").dropna().to_numpy(float)
    post = pd.to_numeric(post_returns, errors="coerce").dropna().to_numpy(float)
    if len(pre) < 2 or len(post) < 2:
        raise ValueError("Each period needs at least two daily returns")
    rng = np.random.default_rng(seed)
    deltas = np.empty(simulations)
    for i in range(simulations):
        pre_sample = _block_sample(pre, len(pre), block_size, rng)
        post_sample = _block_sample(post, len(post), block_size, rng)
        deltas[i] = (post_sample.mean() - pre_sample.mean()) * TRADING_DAYS_PER_YEAR
    return {
        "mean_delta": float(deltas.mean()),
        "ci_low": float(np.quantile(deltas, 0.025)),
        "ci_high": float(np.quantile(deltas, 0.975)),
        "probability_post_gt_pre": float((deltas > 0).mean()),
    }
