#!/usr/bin/env python3
"""Turn raw UQER observations into point-in-time industry factor inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_DATA_ROOT = Path.home() / "Desktop" / "InternData" / "行业景气度项目Data"
DEFAULT_SNAPSHOT_ID = "prosperity-20260812-v1"
DEFAULT_RAW_SNAPSHOT = (
    DEFAULT_DATA_ROOT
    / "raw"
    / "uqer_industry_indicators"
    / f"snapshot={DEFAULT_SNAPSHOT_ID}"
)
DEFAULT_OUTPUT_ROOT = DEFAULT_DATA_ROOT / "processed" / "uqer_industry_prosperity"

CHAIN_LAGS = {"上游": 20, "中游": 10, "下游": 5}
ROLLING_CONFIG = {
    "日": (252, 126),
    "周": (104, 52),
    "旬": (72, 36),
    "月": (60, 24),
    "季": (20, 12),
}
SEASONAL_LAGS = {"日": 252, "周": 52, "旬": 36, "月": 12, "季": 4}

MAPPING_RENAME = {
    "行业代码": "industry_code",
    "行业名称": "industry_name",
    "行业内序号": "industry_order",
    "UQER指标ID": "indic_id",
    "UQER中文名": "indicator_name_cn",
    "产业链位置": "chain_position",
    "产业链判断依据": "chain_rationale",
    "指标职能": "indicator_function",
    "规范统计口径": "normalized_stat_type",
    "原统计类型": "original_stat_type",
    "建议基础处理": "recommended_base_processing",
    "季节性/频率处理": "frequency_processing",
    "方向处理": "direction_processing",
    "可用时点要求": "availability_requirement",
    "频率": "frequency",
    "单位": "unit",
    "地区": "region",
    "国家": "country",
    "数据来源": "source",
    "UQER API": "metadata_api_name",
    "历史开始": "history_start",
    "历史结束": "history_end",
    "更新状态": "update_status",
    "UQER英文名": "indicator_name_en",
}


def _parse_date(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    output = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    compact = text.str.fullmatch(r"\d{8}", na=False)
    output.loc[compact] = pd.to_datetime(
        text.loc[compact], format="%Y%m%d", errors="coerce"
    )
    output.loc[~compact] = pd.to_datetime(text.loc[~compact], errors="coerce")
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, engine="pyarrow", compression="zstd")


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def load_raw_observations(raw_snapshot: Path) -> pd.DataFrame:
    files = sorted((raw_snapshot / "data").rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"原始快照中没有观测 Parquet: {raw_snapshot / 'data'}")
    required = {"indicID", "publishDate", "periodDate", "dataValue", "updateTime"}
    frames: list[pd.DataFrame] = []
    for path in files:
        frame = pd.read_parquet(path)
        if frame.empty and not required.issubset(frame.columns):
            continue
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise ValueError(f"{path} 缺少字段: {missing}")
        frame["__raw_file"] = str(path.relative_to(raw_snapshot))
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=sorted(required))
    return pd.concat(frames, ignore_index=True, sort=False)


def load_mappings(raw_snapshot: Path) -> pd.DataFrame:
    path = raw_snapshot / "indicator_selection.parquet"
    if not path.exists():
        raise FileNotFoundError(f"原始快照缺少指标映射: {path}")
    frame = pd.read_parquet(path)
    # Early snapshots retained this redundant catalog join key in addition to
    # the workbook's authoritative ``UQER API`` column.  Drop it before the
    # bilingual rename so the processed schema never contains duplicate names.
    if "metadata_api_name" in frame.columns and "UQER API" in frame.columns:
        frame = frame.drop(columns=["metadata_api_name"])
    frame = frame.rename(columns=MAPPING_RENAME)
    if frame.columns.duplicated().any():
        duplicates = frame.columns[frame.columns.duplicated()].tolist()
        raise ValueError(f"指标映射存在重复列名: {duplicates}")
    required = {
        "industry_code",
        "industry_name",
        "indic_id",
        "indicator_name_cn",
        "chain_position",
        "normalized_stat_type",
        "frequency",
        "unit",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"指标映射缺少字段: {missing}")
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        frame[column] = frame[column].astype("string").str.strip()
    frame["indic_id"] = frame["indic_id"].astype("string")
    conflicts = []
    for column in ["normalized_stat_type", "frequency", "unit"]:
        counts = frame.groupby("indic_id", dropna=False)[column].nunique(dropna=False)
        if counts.gt(1).any():
            conflicts.extend((column, value) for value in counts[counts.gt(1)].index)
    if conflicts:
        raise ValueError(f"同一指标的处理元数据不一致: {conflicts[:10]}")
    return frame


def load_trade_calendar(raw_snapshot: Path) -> pd.DataFrame:
    path = raw_snapshot / "xshg_trade_calendar.parquet"
    if not path.exists():
        raise FileNotFoundError(f"原始快照缺少交易日历: {path}")
    calendar = pd.read_parquet(path)
    if "trade_date" not in calendar:
        raise ValueError("交易日历缺少 trade_date")
    calendar["trade_date"] = pd.to_datetime(calendar["trade_date"], errors="coerce")
    calendar = calendar.dropna(subset=["trade_date"]).drop_duplicates("trade_date")
    return calendar.sort_values("trade_date", kind="stable").reset_index(drop=True)


def prepare_observations(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    required = {"indicID", "publishDate", "periodDate", "dataValue", "updateTime"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"原始观测缺少字段: {missing}")
    frame = raw.copy()
    audit: dict[str, int] = {"input_rows": int(len(frame))}

    exact_subset = ["indicID", "periodDate", "publishDate", "dataValue", "updateTime"]
    exact = frame.duplicated(exact_subset, keep="first")
    audit["exact_duplicates_removed"] = int(exact.sum())
    frame = frame.loc[~exact].copy()

    frame["indic_id"] = frame["indicID"].astype("string").str.strip()
    frame["period_date"] = _parse_date(frame["periodDate"])
    frame["publish_date"] = _parse_date(frame["publishDate"])
    frame["update_time"] = pd.to_datetime(frame["updateTime"], errors="coerce")
    frame["raw_value"] = pd.to_numeric(frame["dataValue"], errors="coerce")

    missing_publish = frame["publish_date"].isna()
    audit["missing_publish_date_excluded"] = int(missing_publish.sum())
    frame = frame.loc[~missing_publish].copy()

    unusable = (
        frame["indic_id"].isna()
        | frame["period_date"].isna()
        | frame["raw_value"].isna()
    )
    audit["missing_id_period_or_value_excluded"] = int(unusable.sum())
    frame = frame.loc[~unusable].copy()

    impossible = frame["publish_date"].lt(frame["period_date"])
    audit["publish_before_period_excluded"] = int(impossible.sum())
    frame = frame.loc[~impossible].copy()

    frame = frame.sort_values(
        ["indic_id", "period_date", "publish_date", "update_time"],
        kind="stable",
        na_position="first",
    )
    before = len(frame)
    frame = frame.drop_duplicates(
        ["indic_id", "period_date", "publish_date"], keep="last"
    )
    audit["superseded_updates_removed"] = int(before - len(frame))

    before = len(frame)
    frame = frame.drop_duplicates(["indic_id", "period_date"], keep="first")
    audit["later_publication_versions_removed"] = int(before - len(frame))
    audit["output_rows"] = int(len(frame))
    keep = [
        "indic_id",
        "period_date",
        "publish_date",
        "update_time",
        "raw_value",
    ]
    if "__source_api" in frame:
        keep.append("__source_api")
    if "__raw_file" in frame:
        keep.append("__raw_file")
    return frame[keep].reset_index(drop=True), audit


def _annual_change(values: pd.Series, lag: int) -> pd.Series:
    prior = values.shift(lag)
    positive = values.gt(0) & prior.gt(0)
    result = pd.Series(np.nan, index=values.index, dtype=float)
    result.loc[positive] = np.log(values.loc[positive] / prior.loc[positive])
    fallback = ~positive & prior.notna() & prior.ne(0)
    result.loc[fallback] = (
        values.loc[fallback] - prior.loc[fallback]
    ) / prior.loc[fallback].abs()
    return result


def _one_step_change(values: pd.Series) -> pd.Series:
    return _annual_change(values, 1)


def _rate_as_decimal(values: pd.Series, unit: str, index_base: bool = False) -> pd.Series:
    unit_text = str(unit or "")
    if "=100" in unit_text or index_base:
        return values / 100.0 - 1.0
    if "%" in unit_text or "百分点" in unit_text:
        return values / 100.0
    return values.astype(float)


def transform_values(
    raw_values: pd.Series,
    period_dates: pd.Series,
    normalized_stat_type: str,
    frequency: str,
    unit: str,
) -> pd.DataFrame:
    values = pd.to_numeric(raw_values, errors="coerce").astype(float)
    dates = pd.to_datetime(period_dates, errors="coerce")
    lag = SEASONAL_LAGS.get(str(frequency), 12)
    stat = str(normalized_stat_type)
    period_value = values.copy()

    if stat == "年内累计流量":
        years = dates.dt.year
        difference = values.groupby(years).diff()
        first_in_year = ~years.duplicated()
        period_value = difference.where(~first_in_year, values)
        period_value = period_value.where(period_value.ge(0))
        transformed = _annual_change(period_value, lag)
        rule = "deaccumulate_by_calendar_year_then_seasonal_log_change"
    elif stat in {"当期同比增速", "累计同比增速"}:
        transformed = _rate_as_decimal(values, unit)
        rule = "use_reported_yoy_as_decimal"
    elif stat == "当期环比增速":
        transformed = _rate_as_decimal(values, unit)
        rule = "use_reported_mom_as_decimal"
    elif stat == "环比增减":
        transformed = _rate_as_decimal(values, unit)
        rule = "use_reported_change_as_decimal"
    elif stat == "环比指数（上期=100）":
        transformed = _rate_as_decimal(values, unit, index_base=True)
        rule = "convert_chain_index_to_growth"
    elif stat in {"比率水平", "累计比率"}:
        transformed = _rate_as_decimal(values, unit)
        rule = "use_ratio_level_as_decimal"
    elif stat == "指数水平":
        transformed = values.copy()
        rule = "keep_index_level"
    elif stat in {"价格水平", "定基指数", "季调水平值"}:
        transformed = _one_step_change(values)
        rule = "one_period_log_or_robust_change"
    elif stat in {
        "当期流量/数量",
        "存量/规模水平",
        "累计披露的存量/规模",
        "期末存量",
        "一般水平值",
    }:
        transformed = _annual_change(values, lag)
        rule = "seasonal_log_or_robust_change"
    else:
        transformed = _annual_change(values, lag)
        rule = "fallback_seasonal_log_or_robust_change"

    return pd.DataFrame(
        {
            "period_value": period_value,
            "transformed_value": transformed,
            "transformation_rule": rule,
        },
        index=raw_values.index,
    )


def rolling_robust_zscore(
    values: pd.Series, window: int, min_periods: int
) -> pd.Series:
    history = values.shift(1)
    rolling = history.rolling(window=window, min_periods=min_periods)
    center = rolling.median()
    mad = rolling.apply(
        lambda sample: float(np.median(np.abs(sample - np.median(sample)))),
        raw=True,
    )
    robust_scale = mad * 1.4826
    standard_scale = rolling.std(ddof=1)
    scale = robust_scale.where(robust_scale.gt(0), standard_scale)
    result = (values - center) / scale
    return result.where(scale.gt(0)).clip(-5.0, 5.0)


def map_effective_dates(
    publish_dates: pd.Series,
    trade_calendar: pd.DataFrame,
    chain_position: str,
    lag_days: int | None = None,
) -> tuple[pd.Series, pd.Series]:
    if lag_days is None:
        lag_days = CHAIN_LAGS[chain_position]
    dates = pd.to_datetime(trade_calendar["trade_date"], errors="coerce").dropna()
    dates = pd.DatetimeIndex(dates.sort_values().unique())
    publish = pd.to_datetime(publish_dates, errors="coerce")
    available = pd.Series(pd.NaT, index=publish_dates.index, dtype="datetime64[ns]")
    effective = pd.Series(pd.NaT, index=publish_dates.index, dtype="datetime64[ns]")
    valid = publish.notna()
    positions = dates.searchsorted(publish.loc[valid].to_numpy(), side="right")
    valid_indexes = publish.loc[valid].index
    for label, position in zip(valid_indexes, positions):
        if position < len(dates):
            available.loc[label] = dates[position]
        effective_position = position + lag_days
        if effective_position < len(dates):
            effective.loc[label] = dates[effective_position]
    return available, effective


def build_factor_events(
    observations: pd.DataFrame,
    mappings: pd.DataFrame,
    calendar: pd.DataFrame,
    chain_lags: dict[str, int],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    metadata_columns = [
        "indic_id",
        "normalized_stat_type",
        "frequency",
        "unit",
    ]
    metadata = mappings[metadata_columns].drop_duplicates("indic_id")
    metadata = metadata.set_index("indic_id")
    transformed_parts: list[pd.DataFrame] = []
    missing_metadata: list[str] = []

    for indic_id, part in observations.groupby("indic_id", sort=False):
        if indic_id not in metadata.index:
            missing_metadata.append(str(indic_id))
            continue
        row = metadata.loc[indic_id]
        part = part.sort_values(["period_date", "publish_date"], kind="stable").copy()
        transformed = transform_values(
            part["raw_value"],
            part["period_date"],
            str(row["normalized_stat_type"]),
            str(row["frequency"]),
            str(row["unit"]),
        )
        part = part.join(transformed)
        window, minimum = ROLLING_CONFIG[str(row["frequency"])]
        part["factor_value"] = rolling_robust_zscore(
            part["transformed_value"], window, minimum
        )
        part["zscore_window"] = window
        part["zscore_min_periods"] = minimum
        transformed_parts.append(part)

    if transformed_parts:
        transformed_all = pd.concat(transformed_parts, ignore_index=True, sort=False)
    else:
        transformed_all = observations.iloc[0:0].copy()
        for column in [
            "period_value",
            "transformed_value",
            "transformation_rule",
            "factor_value",
            "zscore_window",
            "zscore_min_periods",
        ]:
            transformed_all[column] = pd.Series(dtype="float64")

    events = mappings.merge(transformed_all, on="indic_id", how="inner", validate="many_to_many")
    event_parts: list[pd.DataFrame] = []
    for chain_position, part in events.groupby("chain_position", sort=False):
        available, effective = map_effective_dates(
            part["publish_date"],
            calendar,
            str(chain_position),
            chain_lags[str(chain_position)],
        )
        part = part.copy()
        part["available_date"] = available
        part["chain_lag_trading_days"] = chain_lags[str(chain_position)]
        part["effective_date"] = effective
        event_parts.append(part)
    events = pd.concat(event_parts, ignore_index=True, sort=False) if event_parts else events
    events = events.sort_values(
        ["industry_code", "indic_id", "effective_date", "period_date"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    audit = {
        "indicator_ids_without_mapping": sorted(set(missing_metadata)),
        "event_rows": int(len(events)),
        "non_null_transformed_rows": int(events["transformed_value"].notna().sum()),
        "non_null_factor_rows": int(events["factor_value"].notna().sum()),
        "events_without_calendar_availability": int(events["available_date"].isna().sum()),
        "events_without_effective_date": int(events["effective_date"].isna().sum()),
    }
    return events, audit


def expand_daily(
    events: pd.DataFrame,
    calendar: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    trade_days = calendar.loc[
        calendar["trade_date"].between(start_date, end_date), ["trade_date"]
    ].drop_duplicates()
    event_columns = [
        "effective_date",
        "available_date",
        "publish_date",
        "period_date",
        "raw_value",
        "period_value",
        "transformed_value",
        "factor_value",
        "transformation_rule",
    ]
    daily_parts: list[pd.DataFrame] = []
    keys = ["industry_code", "industry_name", "indic_id", "indicator_name_cn", "chain_position"]
    usable = events.loc[events["effective_date"].notna() & events["factor_value"].notna()].copy()
    for key, part in usable.groupby(keys, sort=False, dropna=False):
        part = part.sort_values(["effective_date", "publish_date", "period_date"], kind="stable")
        part = part.drop_duplicates("effective_date", keep="last")
        first_date = max(start_date, part["effective_date"].min())
        left = trade_days.loc[trade_days["trade_date"].ge(first_date)].copy()
        if left.empty:
            continue
        merged = pd.merge_asof(
            left.sort_values("trade_date"),
            part[event_columns].sort_values("effective_date"),
            left_on="trade_date",
            right_on="effective_date",
            direction="backward",
        )
        for column, value in zip(keys, key):
            merged[column] = value
        daily_parts.append(merged)
    if not daily_parts:
        return pd.DataFrame(columns=["trade_date", *keys, *event_columns])
    daily = pd.concat(daily_parts, ignore_index=True, sort=False)
    return daily[["trade_date", *keys, *event_columns]].sort_values(
        ["trade_date", "industry_code", "indic_id"], kind="stable"
    ).reset_index(drop=True)


def process_snapshot(
    raw_snapshot: Path,
    output_root: Path,
    processed_snapshot_id: str,
    chain_lags: dict[str, int],
) -> Path:
    raw_snapshot = raw_snapshot.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    target = output_root / f"snapshot={processed_snapshot_id}"
    if target.exists():
        raise FileExistsError(f"处理快照已存在: {target}")

    manifest_path = raw_snapshot / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"原始快照缺少 manifest: {manifest_path}")
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    start_date = pd.Timestamp(raw_manifest["date_range"]["start"])
    end_date = pd.Timestamp(raw_manifest["date_range"]["end"])
    mappings = load_mappings(raw_snapshot)
    calendar = load_trade_calendar(raw_snapshot)
    raw = load_raw_observations(raw_snapshot)
    observations, observation_audit = prepare_observations(raw)
    events, event_audit = build_factor_events(
        observations, mappings, calendar, chain_lags
    )
    daily = expand_daily(events, calendar, start_date, end_date)

    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{processed_snapshot_id}-", dir=output_root))
    try:
        _write_parquet(events, staging / "factor_events.parquet")
        daily_root = staging / "factor_daily"
        if daily.empty:
            _write_parquet(daily, daily_root / "part-empty.parquet")
        else:
            for year, part in daily.groupby(daily["trade_date"].dt.year, sort=True):
                _write_parquet(part, daily_root / f"year={int(year)}" / "part-0000.parquet")
        _write_parquet(mappings, staging / "indicator_selection.parquet")

        quality = {
            "processed_at_utc": datetime.now(timezone.utc).isoformat(),
            "raw_snapshot": str(raw_snapshot),
            "raw_manifest_sha256": _sha256(manifest_path),
            "date_range": {
                "start": start_date.strftime("%Y-%m-%d"),
                "end": end_date.strftime("%Y-%m-%d"),
            },
            "chain_lag_trading_days": chain_lags,
            "rolling_config": {
                key: {"window": value[0], "min_periods": value[1]}
                for key, value in ROLLING_CONFIG.items()
            },
            "mapping_rows": int(len(mappings)),
            "mapping_unique_indicators": int(mappings["indic_id"].nunique()),
            "raw_parquet_rows": int(len(raw)),
            "observation_audit": observation_audit,
            "event_audit": event_audit,
            "daily_rows": int(len(daily)),
            "daily_first_date": (
                daily["trade_date"].min().strftime("%Y-%m-%d") if not daily.empty else None
            ),
            "daily_last_date": (
                daily["trade_date"].max().strftime("%Y-%m-%d") if not daily.empty else None
            ),
            "direction_policy": "no_manual_flip_and_no_ts_ic_flip_at_this_stage",
        }
        _write_json(quality, staging / "quality_report.json")
        staging.rename(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 UQER 原始快照处理成严格时点可用的行业景气因子输入。"
    )
    parser.add_argument("--raw-snapshot", type=Path, default=DEFAULT_RAW_SNAPSHOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--processed-snapshot-id", default=DEFAULT_SNAPSHOT_ID)
    parser.add_argument("--lag-upstream", type=int, default=20)
    parser.add_argument("--lag-midstream", type=int, default=10)
    parser.add_argument("--lag-downstream", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lags = {
        "上游": args.lag_upstream,
        "中游": args.lag_midstream,
        "下游": args.lag_downstream,
    }
    if any(value < 0 for value in lags.values()):
        raise ValueError("产业链交易日滞后不能为负数")
    target = process_snapshot(
        args.raw_snapshot,
        args.output_root,
        args.processed_snapshot_id,
        lags,
    )
    report = json.loads((target / "quality_report.json").read_text(encoding="utf-8"))
    print(
        f"处理快照完成: {report['event_audit']['event_rows']} 条事件，"
        f"{report['daily_rows']} 条日频可用记录"
    )
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
