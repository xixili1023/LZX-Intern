#!/usr/bin/env python3
"""Prepare Wind EDB industry indicators for downstream factor research.

The source CSV is a daily wide table whose low-frequency series have already
been carried forward. This script recovers each series' update observations,
applies only the transformations already documented by the project, and then
carries the processed value forward to the daily index again.

Factor selection, TS-IC direction, value-chain transmission lags, cross-series
standardisation and industry aggregation intentionally do not belong here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover - depends on the local runtime
    raise SystemExit(
        "缺少依赖。请先安装 pandas 和 openpyxl："
        "python -m pip install pandas openpyxl"
    ) from exc


DEFAULT_DATA_DIR = Path(
    os.environ.get(
        "INDUSTRY_PROJECT_DATA_ROOT",
        Path.home() / "Desktop" / "InternData" / "行业景气度项目Data",
    )
).expanduser()
DEFAULT_VALUES_FILE = DEFAULT_DATA_DIR / "0803行业指标数据.csv"
DEFAULT_METADATA_FILE = DEFAULT_DATA_DIR / "0803行业指标列表.xlsx"
DEFAULT_OUTPUT_DIR = DEFAULT_DATA_DIR / "processed"

METADATA_COLUMNS = [
    "wind_name",
    "wind_code",
    "industry_code",
    "function_type",
    "calculation_type",
    "ValueChain_type",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="处理行业景气指标，并生成日频指标面板、元数据和质量报告。"
    )
    parser.add_argument("--values", type=Path, default=DEFAULT_VALUES_FILE)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start", help="可选起始日期，格式 YYYY-MM-DD。")
    parser.add_argument("--end", help="可选结束日期，格式 YYYY-MM-DD。")
    parser.add_argument(
        "--availability-lag",
        type=int,
        default=0,
        help="将更新值延后多少个数据行才视为可用；默认 0。",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="发现 CSV 指标缺少元数据或元数据指标缺少数值时终止。",
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_metadata(path: Path) -> pd.DataFrame:
    metadata = pd.read_excel(path, dtype=str)
    missing_columns = sorted(set(METADATA_COLUMNS).difference(metadata.columns))
    if missing_columns:
        raise ValueError(f"指标清单缺少字段: {missing_columns}")

    metadata = metadata[METADATA_COLUMNS].copy()
    metadata = metadata.dropna(subset=["wind_code"])
    for column in METADATA_COLUMNS:
        metadata[column] = metadata[column].astype("string").str.strip()
        metadata.loc[metadata[column].eq(""), column] = pd.NA

    duplicate_pairs = metadata.duplicated(["wind_code", "industry_code"])
    if duplicate_pairs.any():
        examples = metadata.loc[
            duplicate_pairs, ["wind_code", "industry_code"]
        ].head(10)
        raise ValueError(
            "指标清单存在重复的 wind_code × industry_code 映射:\n"
            + examples.to_string(index=False)
        )

    # One indicator may map to several industries, but its transformation
    # attributes must remain consistent across those mappings.
    attributes = ["wind_name", "function_type", "calculation_type"]
    inconsistent = metadata.groupby("wind_code")[attributes].nunique(dropna=False)
    inconsistent = inconsistent[inconsistent.gt(1).any(axis=1)]
    if not inconsistent.empty:
        raise ValueError(
            "同一 wind_code 在多个行业映射中的名称或处理口径不一致: "
            + ", ".join(inconsistent.index[:10])
        )
    return metadata.reset_index(drop=True)


def load_values(
    path: Path, start: str | None, end: str | None
) -> pd.DataFrame:
    values = pd.read_csv(path, low_memory=False)
    if values.shape[1] < 2:
        raise ValueError("指标数据至少需要一列日期和一列指标。")

    date_column = values.columns[0]
    dates = pd.to_datetime(values.pop(date_column), errors="coerce")
    if dates.isna().any():
        bad_rows = (dates.index[dates.isna()] + 2).tolist()[:10]
        raise ValueError(f"日期无法解析，CSV 行号示例: {bad_rows}")
    if dates.duplicated().any():
        duplicates = dates[dates.duplicated()].dt.strftime("%Y-%m-%d").tolist()[:10]
        raise ValueError(f"日期重复: {duplicates}")
    if values.columns.duplicated().any():
        duplicates = values.columns[values.columns.duplicated()].tolist()
        raise ValueError(f"指标列重复: {duplicates[:10]}")

    values.index = pd.DatetimeIndex(dates, name="date")
    values = values.sort_index()
    values = values.apply(pd.to_numeric, errors="coerce")
    if start:
        values = values.loc[pd.Timestamp(start) :]
    if end:
        values = values.loc[: pd.Timestamp(end)]
    if values.empty:
        raise ValueError("指定日期范围内没有数据。")
    return values


def canonical_metadata(metadata: pd.DataFrame) -> pd.DataFrame:
    return metadata.drop_duplicates("wind_code").set_index("wind_code")


def transform_series(
    series: pd.Series, function_type: str | None, calculation_type: str | None
) -> tuple[pd.Series, str, int]:
    # The input has already been forward-filled. Only changed non-null values
    # are true update observations; calculations must happen on those events.
    update_mask = series.notna() & (series.ne(series.shift()) | series.shift().isna())
    events = series.loc[update_mask]

    if function_type == "价格":
        transformed_events = events.pct_change(fill_method=None)
        rule = "price_pct_change"
    elif calculation_type == "累计值":
        previous = events.shift()
        same_year = events.index.year == events.index.to_series().shift().dt.year.to_numpy()
        transformed_events = events - previous
        transformed_events.loc[~same_year] = events.loc[~same_year]
        rule = "cumulative_adjacent_increment"
    elif calculation_type in {"同比", "比率"}:
        transformed_events = events.copy()
        rule = "reported_percent_level"
    else:
        transformed_events = events.copy()
        rule = "reported_level"

    transformed = transformed_events.reindex(series.index).ffill()
    return transformed, rule, int(update_mask.sum())


def process_values(
    values: pd.DataFrame,
    metadata: pd.DataFrame,
    availability_lag: int,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    if availability_lag < 0:
        raise ValueError("availability-lag 不能为负数。")

    canonical = canonical_metadata(metadata)
    processed: dict[str, pd.Series] = {}
    profiles: dict[str, dict[str, Any]] = {}

    for code in values.columns:
        if code in canonical.index:
            function_type = canonical.at[code, "function_type"]
            calculation_type = canonical.at[code, "calculation_type"]
        else:
            function_type = None
            calculation_type = None

        transformed, rule, update_count = transform_series(
            values[code], function_type, calculation_type
        )
        if availability_lag:
            transformed = transformed.shift(availability_lag)
        processed[code] = transformed
        profiles[code] = {
            "transform_rule": rule,
            "update_count": update_count,
            "missing_ratio_raw": round(float(values[code].isna().mean()), 6),
            "missing_ratio_processed": round(float(transformed.isna().mean()), 6),
        }

    return pd.DataFrame(processed, index=values.index), profiles


def enrich_metadata(
    metadata: pd.DataFrame,
    value_codes: list[str],
    profiles: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    enriched = metadata.copy()
    enriched["has_values"] = enriched["wind_code"].isin(value_codes)
    enriched["transform_rule"] = enriched["wind_code"].map(
        {code: item["transform_rule"] for code, item in profiles.items()}
    )
    enriched["update_count"] = enriched["wind_code"].map(
        {code: item["update_count"] for code, item in profiles.items()}
    )
    return enriched


def build_quality_report(
    values_path: Path,
    metadata_path: Path,
    values: pd.DataFrame,
    metadata: pd.DataFrame,
    processed: pd.DataFrame,
    profiles: dict[str, dict[str, Any]],
    availability_lag: int,
) -> dict[str, Any]:
    value_codes = set(values.columns)
    metadata_codes = set(metadata["wind_code"])
    rule_counts = pd.Series(
        [profile["transform_rule"] for profile in profiles.values()]
    ).value_counts()
    return {
        "input": {
            "values_file": str(values_path.resolve()),
            "values_sha256": file_sha256(values_path),
            "metadata_file": str(metadata_path.resolve()),
            "metadata_sha256": file_sha256(metadata_path),
        },
        "date_range": {
            "start": values.index.min().strftime("%Y-%m-%d"),
            "end": values.index.max().strftime("%Y-%m-%d"),
            "rows": int(len(values)),
        },
        "coverage": {
            "value_series": int(values.shape[1]),
            "metadata_rows": int(len(metadata)),
            "metadata_unique_series": int(metadata["wind_code"].nunique()),
            "industries": int(metadata["industry_code"].nunique()),
            "csv_codes_without_metadata": sorted(value_codes - metadata_codes),
            "metadata_codes_without_values": sorted(metadata_codes - value_codes),
            "raw_missing_ratio": round(float(values.isna().to_numpy().mean()), 6),
            "processed_missing_ratio": round(
                float(processed.isna().to_numpy().mean()), 6
            ),
        },
        "processing": {
            "availability_lag_rows": availability_lag,
            "transform_rule_counts": {
                str(key): int(value) for key, value in rule_counts.items()
            },
            "date_semantics": (
                "源文件没有独立发布日期字段；当前将 CSV 日期视为该值的可用日期。"
            ),
            "scope_boundary": (
                "未执行价值链传导滞后、标准化、TS-IC、指标筛选、方向判断或行业聚合。"
            ),
        },
    }


def write_outputs(
    output_dir: Path,
    processed: pd.DataFrame,
    metadata: pd.DataFrame,
    report: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    processed.reset_index().to_csv(
        output_dir / "industry_indicators_daily.csv",
        index=False,
        encoding="utf-8-sig",
        date_format="%Y-%m-%d",
    )
    metadata.to_csv(
        output_dir / "industry_indicator_metadata.csv",
        index=False,
        encoding="utf-8-sig",
    )
    with (output_dir / "industry_indicator_quality.json").open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(report, file, ensure_ascii=False, indent=2)


def main() -> int:
    args = parse_args()
    try:
        metadata = load_metadata(args.metadata)
        values = load_values(args.values, args.start, args.end)
        processed, profiles = process_values(
            values, metadata, args.availability_lag
        )

        value_codes = list(values.columns)
        metadata_codes = set(metadata["wind_code"])
        unmapped = sorted(set(value_codes) - metadata_codes)
        missing_values = sorted(metadata_codes - set(value_codes))
        if args.strict and (unmapped or missing_values):
            raise ValueError(
                f"严格模式校验失败：无元数据指标={unmapped}；无数值指标={missing_values}"
            )

        enriched_metadata = enrich_metadata(metadata, value_codes, profiles)
        report = build_quality_report(
            args.values,
            args.metadata,
            values,
            metadata,
            processed,
            profiles,
            args.availability_lag,
        )
        write_outputs(args.output_dir, processed, enriched_metadata, report)
    except (OSError, ValueError, KeyError) as exc:
        print(f"处理失败: {exc}", file=sys.stderr)
        return 1

    print(f"处理完成：{len(values)} 个日期，{values.shape[1]} 个指标。")
    print(f"输出目录：{args.output_dir.resolve()}")
    if unmapped:
        print(f"警告：{len(unmapped)} 个 CSV 指标缺少元数据，请查看质量报告。")
    if missing_values:
        print(f"提示：{len(missing_values)} 个元数据指标没有数值列。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
