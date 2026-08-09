"""下载全部申万一级行业的月度成份与权重。

运行：python download_uqer_sw_index_weights.py --start-date YYYYMMDD --end-date YYYYMMDD
输出：~/Desktop/InternData/StockData/processed/uqer_sw_index_weights
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from client import DataAPI
from download_uqer_index_daily import (
    SW2014_INDEXES,
    SW2021_INDEXES,
    SW2021_START_DATE,
)


SOURCE_FIELDS = [
    "secID",
    "ticker",
    "secShortName",
    "consID",
    "consShortName",
    "consTickerSymbol",
    "consExchangeCD",
    "effDate",
    "weight",
]

COLUMN_RENAME = {
    "secID": "index_sec_id",
    "ticker": "index_ticker",
    "secShortName": "index_short_name_source",
    "consID": "constituent_sec_id",
    "consTickerSymbol": "constituent_ticker",
    "consShortName": "constituent_short_name",
    "consExchangeCD": "constituent_exchange_cd",
    "effDate": "effective_date",
}

PROCESSED_COLUMNS = [
    "index_sec_id",
    "index_ticker",
    "index_short_name_source",
    "classification_version",
    "classification_name",
    "constituent_sec_id",
    "constituent_ticker",
    "constituent_symbol",
    "constituent_short_name",
    "constituent_exchange_cd",
    "effective_date",
    "weight",
]

PRIMARY_KEY = [
    "classification_version",
    "index_ticker",
    "constituent_sec_id",
    "effective_date",
]

EXCHANGE_SUFFIX = {
    "XSHG": "SH",
    "XSHE": "SZ",
    "XBEI": "BJ",
    "XBSE": "BJ",
    "BSE": "BJ",
}


@dataclass(frozen=True)
class RequestWindow:
    classification_version: str
    start_date: str
    end_date: str
    tickers: tuple[str, ...]


def parse_date(value: str, argument_name: str) -> date:
    if not isinstance(value, str) or re.fullmatch(r"\d{8}", value) is None:
        raise ValueError(f"{argument_name} 必须是有效的 YYYYMMDD 日期")
    try:
        parsed = datetime.strptime(value, "%Y%m%d").date()
    except (TypeError, ValueError) as error:
        raise ValueError(f"{argument_name} 必须是有效的 YYYYMMDD 日期") from error
    return parsed


def build_request_windows(start_date: str, end_date: str) -> list[RequestWindow]:
    start = parse_date(start_date, "start_date")
    end = parse_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")

    transition = parse_date(SW2021_START_DATE, "SW2021_START_DATE")
    periods = [
        ("SW2014", start, min(end, transition - timedelta(days=1))),
        ("SW2021", max(start, transition), end),
    ]
    catalogs = {"SW2014": SW2014_INDEXES, "SW2021": SW2021_INDEXES}
    windows: list[RequestWindow] = []

    for version, period_start, period_end in periods:
        if period_start > period_end:
            continue
        cursor = period_start
        while cursor <= period_end:
            year_end = min(period_end, date(cursor.year, 12, 31))
            windows.append(
                RequestWindow(
                    classification_version=version,
                    start_date=cursor.strftime("%Y%m%d"),
                    end_date=year_end.strftime("%Y%m%d"),
                    tickers=tuple(catalogs[version]),
                )
            )
            cursor = date(cursor.year + 1, 1, 1)
    return windows


class UqerSwIndexWeightsDownloader:
    """下载并校验申万一级行业月度成份与权重。"""

    MAX_TICKERS_PER_REQUEST = 10

    def __init__(
        self,
        start_date: str,
        end_date: str,
        output_root: Path | str | None = None,
        overwrite: bool = False,
        data_api=DataAPI,
    ) -> None:
        build_request_windows(start_date, end_date)
        self.start_date = start_date
        self.end_date = end_date
        self.overwrite = overwrite
        self.data_api = data_api
        self.output_root = Path(output_root) if output_root is not None else (
            Path.home()
            / "Desktop"
            / "InternData"
            / "StockData"
            / "processed"
            / "uqer_sw_index_weights"
        )

    def prepare_data(
        self,
        frame: pd.DataFrame,
        window: RequestWindow,
    ) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=PROCESSED_COLUMNS)

        missing_columns = sorted(set(SOURCE_FIELDS) - set(frame.columns))
        if missing_columns:
            raise ValueError(f"接口缺少字段: {', '.join(missing_columns)}")

        data = frame.loc[:, SOURCE_FIELDS].rename(columns=COLUMN_RENAME).copy()
        data["index_ticker"] = data["index_ticker"].astype("string")
        catalog = (
            SW2021_INDEXES
            if window.classification_version == "SW2021"
            else SW2014_INDEXES
        )
        unknown_tickers = sorted(
            set(data["index_ticker"].dropna().astype(str)) - set(catalog)
        )
        if unknown_tickers:
            raise ValueError(f"分类版本外行业代码: {', '.join(unknown_tickers)}")

        data["classification_version"] = window.classification_version
        data["classification_name"] = data["index_ticker"].map(catalog)
        data["effective_date"] = pd.to_datetime(
            data["effective_date"], errors="coerce"
        ).dt.date
        if data["effective_date"].isna().any():
            raise ValueError("effDate 包含无效日期")

        window_start = parse_date(window.start_date, "window.start_date")
        window_end = parse_date(window.end_date, "window.end_date")
        outside_window = data["effective_date"].map(
            lambda value: value < window_start or value > window_end
        )
        if outside_window.any():
            raise ValueError("effDate 超出当前分类版本请求区间")

        key_source_columns = [
            "index_ticker",
            "constituent_sec_id",
            "constituent_ticker",
            "effective_date",
        ]
        if data[key_source_columns].isna().any().any():
            raise ValueError("主键字段存在缺失值")

        weight = pd.to_numeric(data["weight"], errors="coerce")
        if weight.isna().any():
            raise ValueError("weight 包含缺失或非数值")
        if (weight < 0).any():
            raise ValueError("weight 不能为负数")
        data["weight"] = weight.astype(float)

        string_columns = [
            "index_sec_id",
            "index_ticker",
            "index_short_name_source",
            "classification_version",
            "classification_name",
            "constituent_sec_id",
            "constituent_ticker",
            "constituent_short_name",
            "constituent_exchange_cd",
        ]
        for column in string_columns:
            data[column] = data[column].astype("string")

        def make_symbol(row: pd.Series) -> str:
            suffix = EXCHANGE_SUFFIX.get(str(row["constituent_exchange_cd"]))
            if suffix:
                return f"{row['constituent_ticker']}.{suffix}"
            return str(row["constituent_sec_id"])

        data.insert(
            data.columns.get_loc("constituent_short_name"),
            "constituent_symbol",
            data.apply(make_symbol, axis=1).astype("string"),
        )
        if data.duplicated(PRIMARY_KEY, keep=False).any():
            raise ValueError("数据存在重复主键")

        return (
            data.loc[:, PROCESSED_COLUMNS]
            .sort_values(
                ["effective_date", "index_ticker", "constituent_symbol"],
                kind="mergesort",
            )
            .reset_index(drop=True)
        )

    def ticker_batches(self, tickers: tuple[str, ...]) -> list[tuple[str, ...]]:
        size = self.MAX_TICKERS_PER_REQUEST
        return [
            tickers[start:start + size]
            for start in range(0, len(tickers), size)
        ]

    def download_window(
        self,
        window: RequestWindow,
        call_records: list[dict[str, Any]],
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for ticker_batch in self.ticker_batches(window.tickers):
            call_record: dict[str, Any] = {
                "classification_version": window.classification_version,
                "start_date": window.start_date,
                "end_date": window.end_date,
                "tickers": list(ticker_batch),
                "status": "started",
                "rows": None,
            }
            call_records.append(call_record)
            try:
                result = self.data_api.SwIdxmWeightGet(
                    ticker=",".join(ticker_batch),
                    secID="",
                    beginDate=window.start_date,
                    endDate=window.end_date,
                    field=",".join(SOURCE_FIELDS),
                    pandas="1",
                )
            except Exception as error:
                call_record["status"] = "failed"
                call_record["error_type"] = type(error).__name__
                raise
            if not isinstance(result, pd.DataFrame):
                call_record["status"] = "failed"
                call_record["error_type"] = "TypeError"
                raise TypeError("SwIdxmWeightGet 必须返回 pandas DataFrame")
            call_record["status"] = "success"
            call_record["rows"] = int(len(result))
            if not result.empty:
                frames.append(result)

        if not frames:
            if self.window_includes_month_end(window):
                raise ValueError(
                    f"{window.start_date}-{window.end_date} 覆盖月末但接口未返回数据"
                )
            return pd.DataFrame(columns=PROCESSED_COLUMNS)
        combined = pd.concat(frames, ignore_index=True)
        prepared = self.prepare_data(combined, window)
        self.validate_complete_snapshots(prepared, window)
        return prepared

    @staticmethod
    def window_includes_month_end(window: RequestWindow) -> bool:
        start = parse_date(window.start_date, "window.start_date")
        end = parse_date(window.end_date, "window.end_date")
        cursor = date(
            start.year,
            start.month,
            calendar.monthrange(start.year, start.month)[1],
        )
        return start <= cursor <= end

    def validate_complete_snapshots(
        self,
        data: pd.DataFrame,
        window: RequestWindow,
    ) -> None:
        expected_tickers = set(window.tickers)
        for effective_date, snapshot in data.groupby(
            "effective_date", sort=True
        ):
            actual_tickers = set(snapshot["index_ticker"].astype(str))
            if actual_tickers != expected_tickers:
                missing = sorted(expected_tickers - actual_tickers)
                extra = sorted(actual_tickers - expected_tickers)
                raise ValueError(
                    f"{effective_date} 行业截面不完整；"
                    f"缺失={','.join(missing) or '无'}；"
                    f"多余={','.join(extra) or '无'}"
                )

        invalid_totals = [
            record
            for record in self.weight_quality(data)
            if record["scale"] == "unrecognized"
        ]
        if invalid_totals:
            first = invalid_totals[0]
            raise ValueError(
                f"{first['effective_date']} {first['index_ticker']} "
                f"权重合计异常: {first['weight_total']}"
            )

    def get_output_path(self, effective_date: date) -> Path:
        date_string = effective_date.strftime("%Y%m%d")
        return (
            self.output_root
            / f"year={date_string[:4]}"
            / f"month={date_string[4:6]}"
            / f"{date_string}.parquet"
        )

    def atomic_write_parquet(self, frame: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.stem}.{os.getpid()}.tmp.parquet")
        try:
            frame.to_parquet(
                temporary,
                index=False,
                engine="pyarrow",
                compression="zstd",
            )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def save_window(
        self,
        data: pd.DataFrame,
        written_files: list[dict[str, Any]],
        skipped_files: list[dict[str, Any]],
    ) -> None:
        if data.empty:
            return
        for effective_date, daily_data in data.groupby(
            "effective_date", sort=True
        ):
            output_path = self.get_output_path(effective_date)
            record = {
                "path": str(output_path),
                "effective_date": effective_date.isoformat(),
                "rows": int(len(daily_data)),
            }
            if output_path.exists() and not self.overwrite:
                skipped_files.append(record)
                continue
            self.atomic_write_parquet(daily_data.reset_index(drop=True), output_path)
            written_files.append(record)

    @staticmethod
    def classify_weight_scale(total: float) -> str:
        if abs(total - 1.0) <= 0.01:
            return "ratio"
        if abs(total - 100.0) <= 0.5:
            return "percent"
        return "unrecognized"

    def weight_quality(self, data: pd.DataFrame) -> list[dict[str, Any]]:
        if data.empty:
            return []
        group_columns = [
            "classification_version",
            "index_ticker",
            "effective_date",
        ]
        totals = data.groupby(group_columns, observed=True)["weight"].sum()
        return [
            {
                "classification_version": version,
                "index_ticker": ticker,
                "effective_date": effective_date.isoformat(),
                "weight_total": float(total),
                "scale": self.classify_weight_scale(float(total)),
            }
            for (version, ticker, effective_date), total in totals.items()
        ]

    def atomic_write_json(self, payload: dict[str, Any], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def build_manifest(
        self,
        status: str,
        call_records: list[dict[str, Any]],
        written_files: list[dict[str, Any]],
        skipped_files: list[dict[str, Any]],
        quality_records: list[dict[str, Any]],
        unique_tickers: set[str],
        unique_dates: set[str],
        completed_windows: list[dict[str, str]],
        failure: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        scale_counts = Counter(record["scale"] for record in quality_records)
        rows_downloaded = sum(
            int(record["rows"] or 0) for record in call_records
        )
        return {
            "status": status,
            "source_api": "SwIdxmWeightGet",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "parameters": {
                "start_date": self.start_date,
                "end_date": self.end_date,
                "output_root": str(self.output_root),
                "overwrite": self.overwrite,
            },
            "calls": call_records,
            "completed_windows": completed_windows,
            "files": {
                "written": written_files,
                "skipped": skipped_files,
            },
            "summary": {
                "api_calls": len(call_records),
                "rows_downloaded": rows_downloaded,
                "files_written": len(written_files),
                "files_skipped": len(skipped_files),
                "unique_index_tickers": len(unique_tickers),
                "unique_effective_dates": len(unique_dates),
            },
            "quality": {
                "weight_scale_counts": dict(sorted(scale_counts.items())),
                "weight_totals": quality_records,
            },
            "failure": failure,
        }

    def run(self) -> Path:
        call_records: list[dict[str, Any]] = []
        written_files: list[dict[str, Any]] = []
        skipped_files: list[dict[str, Any]] = []
        quality_records: list[dict[str, Any]] = []
        unique_tickers: set[str] = set()
        unique_dates: set[str] = set()
        completed_windows: list[dict[str, str]] = []
        current_window: RequestWindow | None = None
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        manifest_path = self.output_root / "manifests" / f"run={timestamp}.json"

        windows = build_request_windows(self.start_date, self.end_date)
        try:
            for window in windows:
                current_window = window
                data = self.download_window(window, call_records)
                if not data.empty:
                    unique_tickers.update(data["index_ticker"].dropna().astype(str))
                    unique_dates.update(
                        value.isoformat()
                        for value in data["effective_date"].unique()
                    )
                    quality_records.extend(self.weight_quality(data))
                self.save_window(data, written_files, skipped_files)
                completed_windows.append(
                    {
                        "classification_version": window.classification_version,
                        "start_date": window.start_date,
                        "end_date": window.end_date,
                    }
                )
        except Exception as error:
            failure = {
                "error_type": type(error).__name__,
                "window": None
                if current_window is None
                else {
                    "classification_version": current_window.classification_version,
                    "start_date": current_window.start_date,
                    "end_date": current_window.end_date,
                },
            }
            manifest = self.build_manifest(
                "failed",
                call_records,
                written_files,
                skipped_files,
                quality_records,
                unique_tickers,
                unique_dates,
                completed_windows,
                failure,
            )
            try:
                self.atomic_write_json(manifest, manifest_path)
            except Exception:
                pass
            raise

        manifest = self.build_manifest(
            "success",
            call_records,
            written_files,
            skipped_files,
            quality_records,
            unique_tickers,
            unique_dates,
            completed_windows,
        )
        self.atomic_write_json(manifest, manifest_path)
        return manifest_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载全部申万一级行业的月度成份与权重。"
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="开始日期，格式为 YYYYMMDD",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="结束日期，格式为 YYYYMMDD",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="可选：自定义数据保存目录",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已经存在的生效日文件",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    downloader = UqerSwIndexWeightsDownloader(
        start_date=args.start_date,
        end_date=args.end_date,
        output_root=args.output_root,
        overwrite=args.overwrite,
    )
    manifest_path = downloader.run()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = manifest["summary"]
    print(
        f"完成：{summary['api_calls']} 次请求，"
        f"{summary['rows_downloaded']} 行，"
        f"写入 {summary['files_written']} 个文件，"
        f"跳过 {summary['files_skipped']} 个文件。"
    )
    print(f"运行清单：{manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
