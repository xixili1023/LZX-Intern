#!/usr/bin/env python3
"""Profile one immutable UQER macro/industry indicator snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查 UQER 行业指标快照的字段、覆盖、缺失和重复。"
    )
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_metadata(snapshot: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted((snapshot / "metadata").rglob("*.parquet")):
        frame = pd.read_parquet(path)
        frame["__catalog_api"] = path.stem
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def read_observations(snapshot: Path) -> pd.DataFrame:
    paths = sorted((snapshot / "data").rglob("*.parquet"))
    if not paths:
        return pd.DataFrame()
    return pd.concat(
        [pd.read_parquet(path) for path in paths],
        ignore_index=True,
        sort=False,
    )


def snapshot_apis(snapshot: Path) -> list[str]:
    metadata_apis = {
        path.stem for path in (snapshot / "metadata").rglob("*.parquet")
    }
    data_apis = {
        path.parent.name.removeprefix("api=")
        for path in (snapshot / "data").rglob("*.parquet")
    }
    return sorted(metadata_apis | data_apis)


def count_missing(frame: pd.DataFrame, column: str) -> int:
    if column not in frame:
        return len(frame)
    values = frame[column].astype("string").str.strip()
    return int(values.isna().sum() + values.eq("").sum())


def parse_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype("string"), format="mixed", errors="coerce")


def api_quality(
    metadata: pd.DataFrame, data: pd.DataFrame, expected_apis: list[str]
) -> pd.DataFrame:
    metadata_rows: list[dict[str, Any]] = []
    if not metadata.empty:
        for api_name, part in metadata.groupby("__catalog_api", dropna=False):
            ids = part.get("indicID", pd.Series(dtype="string")).astype("string")
            metadata_rows.append(
                {
                    "api_name": str(api_name),
                    "metadata_rows": int(len(part)),
                    "metadata_unique_indicators": int(ids.nunique()),
                    "metadata_duplicate_indicator_rows": int(ids.duplicated().sum()),
                }
            )
    meta_summary = pd.DataFrame(metadata_rows)

    data_rows: list[dict[str, Any]] = []
    if not data.empty:
        for api_name, part in data.groupby("__source_api", dropna=False):
            numeric = pd.to_numeric(part.get("dataValue"), errors="coerce")
            period = parse_datetime(part.get("periodDate"))
            keys = [
                column
                for column in ["indicID", "periodDate", "publishDate", "dataValue"]
                if column in part
            ]
            data_rows.append(
                {
                    "api_name": str(api_name),
                    "observation_rows": int(len(part)),
                    "observation_unique_indicators": int(
                        part.get("indicID", pd.Series(dtype="string")).nunique()
                    ),
                    "period_start": (
                        period.min().strftime("%Y-%m-%d")
                        if period.notna().any()
                        else None
                    ),
                    "period_end": (
                        period.max().strftime("%Y-%m-%d")
                        if period.notna().any()
                        else None
                    ),
                    "publish_date_missing": count_missing(part, "publishDate"),
                    "period_date_missing": count_missing(part, "periodDate"),
                    "data_value_missing": count_missing(part, "dataValue"),
                    "data_value_non_numeric": int(
                        numeric.isna().sum() - count_missing(part, "dataValue")
                    ),
                    "exact_duplicate_rows": (
                        int(part.duplicated(keys).sum()) if keys else 0
                    ),
                }
            )
    data_summary = pd.DataFrame(data_rows)

    base = pd.DataFrame({"api_name": expected_apis})
    if not meta_summary.empty:
        base = base.merge(meta_summary, on="api_name", how="outer")
    if not data_summary.empty:
        base = base.merge(data_summary, on="api_name", how="outer")
    return base.sort_values("api_name").reset_index(drop=True)


def indicator_profile(metadata: pd.DataFrame, data: pd.DataFrame) -> pd.DataFrame:
    metadata_columns = [
        "indicID",
        "indicName",
        "frequency",
        "unit",
        "statType",
        "region",
        "country",
        "currency",
        "infoSource",
        "dataApiName",
        "beginDate",
        "endDate",
        "isUpdate",
    ]
    available = [column for column in metadata_columns if column in metadata]
    if available:
        meta = metadata[available].drop_duplicates("indicID", keep="first")
    else:
        meta = pd.DataFrame(columns=["indicID"])

    if data.empty or "indicID" not in data:
        return meta
    working = data.copy()
    working["__period"] = parse_datetime(working["periodDate"])
    obs = (
        working.groupby("indicID", dropna=False)
        .agg(
            observation_rows=("indicID", "size"),
            period_start=("__period", "min"),
            period_end=("__period", "max"),
            publish_date_missing=(
                "publishDate",
                lambda value: count_missing(
                    pd.DataFrame({"publishDate": value}), "publishDate"
                ),
            ),
        )
        .reset_index()
    )
    for column in ["period_start", "period_end"]:
        obs[column] = obs[column].dt.strftime("%Y-%m-%d")
    return meta.merge(obs, on="indicID", how="outer")


def latest_observations(metadata: pd.DataFrame, data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data
    output = data.copy()
    output["__period"] = parse_datetime(output["periodDate"])
    output = output.sort_values(["indicID", "__period", "publishDate"])
    output = output.groupby("indicID", as_index=False).tail(3)
    names = (
        metadata[["indicID", "indicName"]].drop_duplicates("indicID")
        if {"indicID", "indicName"}.issubset(metadata.columns)
        else pd.DataFrame(columns=["indicID", "indicName"])
    )
    keep = [
        "indicID",
        "indicName",
        "__source_api",
        "publishDate",
        "periodDate",
        "dataValue",
        "updateTime",
    ]
    return output.merge(names, on="indicID", how="left").reindex(columns=keep)


def build_report(
    snapshot: Path,
    metadata: pd.DataFrame,
    data: pd.DataFrame,
    quality: pd.DataFrame,
) -> dict[str, Any]:
    publish_lag: pd.Series = pd.Series(dtype="float64")
    if not data.empty and {"publishDate", "periodDate"}.issubset(data.columns):
        publish_lag = (
            parse_datetime(data["publishDate"]) - parse_datetime(data["periodDate"])
        ).dt.total_seconds() / 86400
    valid_lag = publish_lag.dropna()
    manifest = snapshot / "manifest.json"
    return {
        "snapshot": str(snapshot.resolve()),
        "manifest_sha256": sha256_file(manifest) if manifest.exists() else None,
        "metadata_rows": int(len(metadata)),
        "metadata_unique_indicators": int(
            metadata.get("indicID", pd.Series(dtype="string")).nunique()
        ),
        "observation_rows": int(len(data)),
        "observation_unique_indicators": int(
            data.get("indicID", pd.Series(dtype="string")).nunique()
        ),
        "apis_queried": int(len(quality)),
        "apis_with_metadata": int(
            quality.get("metadata_rows", pd.Series()).gt(0).sum()
        ),
        "apis_with_observations": int(
            quality.get("observation_rows", pd.Series()).fillna(0).gt(0).sum()
        ),
        "missing": {
            column: count_missing(data, column)
            for column in ["publishDate", "periodDate", "dataValue", "updateTime"]
        },
        "publish_minus_period_days": {
            "valid_rows": int(len(valid_lag)),
            "negative_rows": int(valid_lag.lt(0).sum()),
            "median": round(float(valid_lag.median()), 3) if len(valid_lag) else None,
            "p10": round(float(valid_lag.quantile(0.10)), 3) if len(valid_lag) else None,
            "p90": round(float(valid_lag.quantile(0.90)), 3) if len(valid_lag) else None,
        },
        "interpretation_notes": [
            "publishDate 缺失时不能把 updateTime 无条件当作首次可用日。",
            (
                "periodDate 常是月末或季末标签，publishDate 可能早于"
                "该标签日，负滞后不必然是错误。"
            ),
            (
                "原始 dataValue 保持接口返回类型，分析层再做"
                "数值转换与单位换算。"
            ),
        ],
    }


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    if not args.snapshot.is_dir():
        raise FileNotFoundError(f"快照目录不存在: {args.snapshot}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    metadata = read_metadata(args.snapshot)
    data = read_observations(args.snapshot)
    quality = api_quality(metadata, data, snapshot_apis(args.snapshot))
    indicators = indicator_profile(metadata, data)
    latest = latest_observations(metadata, data)
    report = build_report(args.snapshot, metadata, data, quality)

    quality.to_csv(
        args.output_dir / "api_quality.csv", index=False, encoding="utf-8-sig"
    )
    indicators.to_csv(
        args.output_dir / "indicator_profile.csv", index=False, encoding="utf-8-sig"
    )
    latest.to_csv(
        args.output_dir / "latest_observations.csv", index=False, encoding="utf-8-sig"
    )
    atomic_write_json(report, args.output_dir / "quality.json")
    print(
        f"完成：{report['metadata_unique_indicators']} 个元数据指标，"
        f"{report['observation_rows']} 行观测。"
    )
    print(f"输出：{args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
