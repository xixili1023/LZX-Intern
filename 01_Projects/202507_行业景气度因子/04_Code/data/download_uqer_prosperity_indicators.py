#!/usr/bin/env python3
"""Download the approved UQER prosperity indicators into an immutable raw snapshot."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_WORKBOOK = (
    PROJECT_ROOT
    / "02_Factors"
    / "01_行业景气度因子"
    / "UQER行业景气指标清单_最终版.xlsx"
)
DEFAULT_CATALOG = SCRIPT_DIR / "uqer_industry_api_catalog.csv"
DEFAULT_DATA_ROOT = Path.home() / "Desktop" / "InternData" / "行业景气度项目Data"
DEFAULT_OUTPUT_ROOT = DEFAULT_DATA_ROOT / "raw" / "uqer_industry_indicators"
DEFAULT_SNAPSHOT_ID = "prosperity-20260812-v1"

REQUIRED_MAPPING_COLUMNS = [
    "行业代码",
    "行业名称",
    "UQER指标ID",
    "UQER中文名",
    "产业链位置",
    "规范统计口径",
    "原统计类型",
    "频率",
    "单位",
    "UQER API",
]
VALID_CHAIN_POSITIONS = {"上游", "中游", "下游"}


def _import_generic_downloader():
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    import download_uqer_industry_indicators as generic

    return generic


def _clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace("", pd.NA)


def load_indicator_mappings(path: Path) -> pd.DataFrame:
    frame = pd.read_excel(
        path,
        sheet_name="最终指标表",
        dtype=str,
        keep_default_na=False,
    )
    missing = sorted(set(REQUIRED_MAPPING_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"最终指标表缺少字段: {missing}")

    for column in frame.columns:
        if frame[column].dtype == object:
            frame[column] = _clean_text(frame[column])
    frame["UQER指标ID"] = _clean_text(frame["UQER指标ID"])
    frame["行业代码"] = _clean_text(frame["行业代码"])
    frame = frame.dropna(subset=["行业代码", "UQER指标ID", "UQER API"])

    invalid_chain = sorted(
        set(frame["产业链位置"].dropna()).difference(VALID_CHAIN_POSITIONS)
    )
    if invalid_chain:
        raise ValueError(f"产业链位置存在未知值: {invalid_chain}")
    duplicate = frame.duplicated(["行业代码", "UQER指标ID"], keep=False)
    if duplicate.any():
        rows = frame.loc[duplicate, ["行业代码", "UQER指标ID"]]
        raise ValueError(f"存在重复的行业×指标映射: {rows.to_dict('records')[:5]}")
    if frame.empty:
        raise ValueError("最终指标表没有可下载指标")
    return frame.reset_index(drop=True)


def load_api_crosswalk(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"metadata_api_name", "api_name", "enabled"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"接口清单缺少字段: {missing}")
    enabled = frame["enabled"].astype(str).str.strip().str.lower().isin(
        {"1", "true", "yes", "y"}
    )
    result = frame.loc[enabled, ["metadata_api_name", "api_name"]].copy()
    result = result.apply(_clean_text).dropna().drop_duplicates()
    conflicts = result.groupby("metadata_api_name")["api_name"].nunique()
    conflicts = conflicts.loc[conflicts.gt(1)]
    if not conflicts.empty:
        raise ValueError(f"元数据 API 映射冲突: {conflicts.index.tolist()}")
    return result.drop_duplicates("metadata_api_name").reset_index(drop=True)


def attach_data_apis(
    mappings: pd.DataFrame, crosswalk: pd.DataFrame
) -> pd.DataFrame:
    result = mappings.merge(
        crosswalk,
        how="left",
        left_on="UQER API",
        right_on="metadata_api_name",
        validate="many_to_one",
    )
    missing = sorted(result.loc[result["api_name"].isna(), "UQER API"].unique())
    if missing:
        raise ValueError(f"以下 UQER API 没有启用的数据接口映射: {missing}")
    return result.drop(columns=["metadata_api_name"]).rename(
        columns={"api_name": "data_api_name"}
    )


def build_download_requests(mappings: pd.DataFrame) -> pd.DataFrame:
    result = mappings[["UQER指标ID", "data_api_name"]].rename(
        columns={
            "UQER指标ID": "uqer_indic_id",
            "data_api_name": "uqer_api_name",
        }
    )
    return result.drop_duplicates().sort_values(
        ["uqer_api_name", "uqer_indic_id"], kind="stable"
    ).reset_index(drop=True)


def download_trade_calendar(
    data_api: Any, start_date: str, end_date: str
) -> pd.DataFrame:
    frame = data_api.TradeCalGet(
        exchangeCD="XSHG",
        beginDate=start_date,
        endDate=end_date,
        field="calendarDate,isOpen",
        pandas="1",
    )
    required = {"calendarDate", "isOpen"}
    if not required.issubset(frame.columns):
        raise ValueError(f"交易日历缺少字段: {sorted(required.difference(frame.columns))}")
    output = frame.copy()
    output["trade_date"] = pd.to_datetime(output["calendarDate"], errors="coerce")
    output["is_open"] = pd.to_numeric(output["isOpen"], errors="coerce")
    output = output.loc[output["trade_date"].notna() & output["is_open"].eq(1)]
    output = output[["trade_date", "is_open"]].drop_duplicates("trade_date")
    output = output.sort_values("trade_date", kind="stable").reset_index(drop=True)
    if output.empty:
        raise ValueError("XSHG 交易日历为空")
    return output


def run_download(args: argparse.Namespace, data_api: Any | None = None) -> Path:
    generic = _import_generic_downloader()
    mappings = attach_data_apis(
        load_indicator_mappings(args.workbook),
        load_api_crosswalk(args.catalog),
    )
    requests = build_download_requests(mappings)
    if data_api is None:
        data_api = generic.load_data_api()

    output_root = args.output_root.expanduser().resolve()
    snapshot_root = output_root / f"snapshot={args.snapshot_id}"
    if snapshot_root.exists():
        raise FileExistsError(f"原始快照已存在: {snapshot_root}")

    calendar_end = (
        datetime.strptime(args.end_date, "%Y%m%d") + timedelta(days=60)
    ).strftime("%Y%m%d")
    calendar = download_trade_calendar(data_api, args.start_date, calendar_end)

    with tempfile.TemporaryDirectory(prefix="uqer-prosperity-selection-") as temp:
        selection_path = Path(temp) / "selection.csv"
        requests.to_csv(selection_path, index=False)
        downloader = generic.UqerIndustryDownloader(
            catalog_path=args.catalog,
            output_root=output_root,
            snapshot_id=args.snapshot_id,
            start_date=args.start_date,
            end_date=args.end_date,
            batch_size=args.batch_size,
            selection_path=selection_path,
            fail_fast=False,
            data_api=data_api,
        )
        snapshot = downloader.run("selected")

    generic.atomic_write_parquet(mappings, snapshot / "indicator_selection.parquet")
    generic.atomic_write_parquet(requests, snapshot / "download_requests.parquet")
    generic.atomic_write_parquet(calendar, snapshot / "xshg_trade_calendar.parquet")
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["selection_file"] = "download_requests.parquet"
    manifest["selection_sha256"] = generic.sha256_file(
        snapshot / "download_requests.parquet"
    )
    manifest["approved_indicator_workbook"] = str(args.workbook.resolve())
    manifest["approved_indicator_workbook_sha256"] = generic.sha256_file(args.workbook)
    manifest["prosperity_mapping_rows"] = int(len(mappings))
    manifest["prosperity_unique_indicators"] = int(mappings["UQER指标ID"].nunique())
    manifest["prosperity_unique_requests"] = int(len(requests))
    manifest["trade_calendar"] = {
        "exchange": "XSHG",
        "start": calendar["trade_date"].min().strftime("%Y-%m-%d"),
        "end": calendar["trade_date"].max().strftime("%Y-%m-%d"),
        "open_days": int(len(calendar)),
    }
    generic.atomic_write_json(manifest, manifest_path)
    downloader.manifest = manifest
    return snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载最终清单中的 UQER 行业景气指标。"
    )
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--snapshot-id", default=DEFAULT_SNAPSHOT_ID)
    parser.add_argument("--start-date", default="20150101")
    parser.add_argument("--end-date", default="20260812")
    parser.add_argument("--batch-size", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if datetime.strptime(args.start_date, "%Y%m%d") > datetime.strptime(
        args.end_date, "%Y%m%d"
    ):
        raise ValueError("start-date 不能晚于 end-date")
    snapshot = run_download(args)
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    summary = manifest["summary"]
    print(
        f"原始快照完成: {manifest['prosperity_unique_indicators']} 个指标，"
        f"{summary['observation_rows']} 行观测，{summary['failed_calls']} 个失败请求"
    )
    print(snapshot)
    return 1 if summary["failed_calls"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
