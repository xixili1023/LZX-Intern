#!/usr/bin/env python3
"""Download UQER macro and industry indicators through the local gateway.

The downloader is deliberately configuration-driven: one executable handles
all compatible EcoData* interfaces, while the catalog records which interface
belongs to which research category.  Raw responses are split by API and query
batch so a failed request can be diagnosed or rerun without creating hundreds
of one-indicator scripts or one fragile monolithic file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOG = Path(__file__).with_name("uqer_industry_api_catalog.csv")
DEFAULT_DATA_ROOT = Path(
    os.environ.get(
        "INDUSTRY_PROJECT_DATA_ROOT",
        Path.home() / "Desktop" / "InternData" / "行业景气度项目Data",
    )
).expanduser()
DEFAULT_OUTPUT_ROOT = DEFAULT_DATA_ROOT / "raw" / "uqer_industry_indicators"
CLIENT_DIR = REPOSITORY_ROOT / "02_Assets" / "Code" / "data_acquisition"

METADATA_FIELDS = [
    "indicID",
    "indicName",
    "nameEN",
    "dyCD",
    "parentID",
    "isList",
    "frequency",
    "unit",
    "statType",
    "accuracy",
    "region",
    "country",
    "currency",
    "importance",
    "infoSource",
    "memoCN",
    "dataApiID",
    "dataApiName",
    "beginDate",
    "endDate",
    "isUpdate",
]

DATA_FIELDS = [
    "indicID",
    "publishDate",
    "periodDate",
    "dataValue",
    "updateTime",
]

CATALOG_COLUMNS = [
    "scope",
    "category",
    "api_name",
    "metadata_api_name",
    "sample_indic_id",
    "enabled",
    "review_status",
    "review_note",
]

SELECTION_COLUMNS = ["uqer_indic_id", "uqer_api_name"]


@dataclass(frozen=True)
class CatalogRow:
    scope: str
    category: str
    api_name: str
    metadata_api_name: str
    sample_indic_id: str
    enabled: bool
    review_status: str
    review_note: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_snapshot_id() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_enabled(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def load_catalog(path: Path) -> list[CatalogRow]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = sorted(set(CATALOG_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"接口清单缺少字段: {missing}")

    rows: list[CatalogRow] = []
    for record in frame[CATALOG_COLUMNS].to_dict("records"):
        row = CatalogRow(
            scope=record["scope"].strip(),
            category=record["category"].strip(),
            api_name=record["api_name"].strip(),
            metadata_api_name=record["metadata_api_name"].strip(),
            sample_indic_id=record["sample_indic_id"].strip(),
            enabled=parse_enabled(record["enabled"]),
            review_status=record["review_status"].strip(),
            review_note=record["review_note"].strip(),
        )
        if not row.api_name or not row.metadata_api_name:
            raise ValueError("接口清单存在空 api_name 或 metadata_api_name")
        rows.append(row)
    return rows


def load_selection(path: Path) -> dict[str, list[str]]:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = sorted(set(SELECTION_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"指标选择表缺少字段: {missing}")
    if "download_enabled" in frame:
        frame = frame.loc[frame["download_enabled"].map(parse_enabled)]

    frame = frame[SELECTION_COLUMNS].copy()
    for column in SELECTION_COLUMNS:
        frame[column] = frame[column].str.strip()
    frame = frame.loc[
        frame["uqer_indic_id"].ne("") & frame["uqer_api_name"].ne("")
    ].drop_duplicates()
    if frame.empty:
        raise ValueError("指标选择表没有启用的 UQER 指标")

    groups: dict[str, list[str]] = {}
    for api_name, part in frame.groupby("uqer_api_name", sort=False):
        groups[str(api_name)] = unique_preserving_order(
            part["uqer_indic_id"].tolist()
        )
    return groups


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    if size <= 0:
        raise ValueError("batch-size 必须大于 0")
    for start in range(0, len(values), size):
        yield values[start : start + size]


def load_data_api() -> Any:
    if not (CLIENT_DIR / "client.py").exists():
        raise FileNotFoundError(
            f"缺少本地网关客户端: {CLIENT_DIR / 'client.py'}"
        )
    sys.path.insert(0, str(CLIENT_DIR))
    from client import DataAPI  # type: ignore

    return DataAPI


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(
        temporary,
        index=False,
        engine="pyarrow",
        compression="zstd",
    )
    temporary.replace(path)


def value_range(frame: pd.DataFrame, column: str) -> dict[str, str | None]:
    if column not in frame or frame[column].dropna().empty:
        return {"min": None, "max": None}
    values = frame[column].astype("string").dropna()
    return {"min": str(values.min()), "max": str(values.max())}


class UqerIndustryDownloader:
    """Download metadata and long-form observations for catalogued APIs."""

    def __init__(
        self,
        catalog_path: Path,
        output_root: Path,
        snapshot_id: str,
        start_date: str,
        end_date: str,
        batch_size: int = 20,
        selected_apis: set[str] | None = None,
        selection_path: Path | None = None,
        include_disabled: bool = False,
        fail_fast: bool = False,
        allow_all_indicators: bool = False,
        data_api: Any | None = None,
    ) -> None:
        self.catalog_path = catalog_path
        self.output_root = output_root
        self.snapshot_id = snapshot_id
        self.snapshot_root = output_root / f"snapshot={snapshot_id}"
        self.start_date = start_date
        self.end_date = end_date
        self.batch_size = batch_size
        self.selected_apis = selected_apis
        self.selection_path = selection_path
        self.selection = (
            load_selection(selection_path) if selection_path else None
        )
        self.include_disabled = include_disabled
        self.fail_fast = fail_fast
        self.allow_all_indicators = allow_all_indicators
        self.data_api = data_api
        self.downloaded_at = utc_now().isoformat()
        self.catalog = load_catalog(catalog_path)
        self.manifest: dict[str, Any] = {
            "snapshot_id": snapshot_id,
            "downloaded_at_utc": self.downloaded_at,
            "catalog_file": str(catalog_path.resolve()),
            "catalog_sha256": sha256_file(catalog_path),
            "selection_file": (
                str(selection_path.resolve()) if selection_path else None
            ),
            "selection_sha256": (
                sha256_file(selection_path) if selection_path else None
            ),
            "date_range": {"start": start_date, "end": end_date},
            "batch_size": batch_size,
            "catalog_rows": [asdict(row) for row in self.catalog],
            "calls": [],
            "errors": [],
        }

    def eligible_rows(self) -> list[CatalogRow]:
        rows = [
            row for row in self.catalog if row.enabled or self.include_disabled
        ]
        if self.selected_apis:
            rows = [row for row in rows if row.api_name in self.selected_apis]
        if not rows:
            raise ValueError("筛选后没有可下载的 API")
        return rows

    def api_groups(self) -> dict[str, list[CatalogRow]]:
        groups: dict[str, list[CatalogRow]] = {}
        for row in self.eligible_rows():
            groups.setdefault(row.api_name, []).append(row)
        return groups

    def ensure_snapshot_is_new(self) -> None:
        if self.snapshot_root.exists():
            raise FileExistsError(
                f"快照目录已存在: {self.snapshot_root}；请更换 --snapshot-id"
            )
        self.snapshot_root.mkdir(parents=True)

    def api_client(self) -> Any:
        if self.data_api is None:
            self.data_api = load_data_api()
        return self.data_api

    def record_call(
        self,
        api_name: str,
        purpose: str,
        kwargs: dict[str, Any],
        frame: pd.DataFrame,
        output_path: Path,
    ) -> None:
        self.manifest["calls"].append(
            {
                "api_name": api_name,
                "purpose": purpose,
                "kwargs": kwargs,
                "rows": int(len(frame)),
                "columns": list(map(str, frame.columns)),
                "period_date": value_range(frame, "periodDate"),
                "publish_date": value_range(frame, "publishDate"),
                "output_file": str(output_path.relative_to(self.snapshot_root)),
                "output_sha256": sha256_file(output_path),
            }
        )

    def record_error(
        self,
        api_name: str,
        purpose: str,
        kwargs: dict[str, Any],
        error: Exception,
    ) -> None:
        self.manifest["errors"].append(
            {
                "api_name": api_name,
                "purpose": purpose,
                "kwargs": kwargs,
                "error_type": type(error).__name__,
                "message": str(error),
            }
        )

    def write_frame(
        self,
        frame: pd.DataFrame,
        output_path: Path,
        source_api: str,
        query_batch: int | None,
    ) -> pd.DataFrame:
        output = frame.copy()
        output["__source_api"] = source_api
        output["__downloaded_at_utc"] = self.downloaded_at
        if query_batch is not None:
            output["__query_batch"] = query_batch
        atomic_write_parquet(output, output_path)
        return output

    def fetch_metadata(
        self,
        api_name: str,
        metadata_api_name: str,
        indic_ids: list[str] | None,
    ) -> pd.DataFrame:
        kwargs = {
            "indicID": ",".join(indic_ids or []),
            "parentID": "",
            "indicName": "",
            "dyCD": "",
            "isUpdate": "",
            "dataApiName": "" if indic_ids else metadata_api_name,
            "updateTime": "",
            "field": ",".join(METADATA_FIELDS),
            "pandas": "1",
        }
        purpose = "indicator_metadata" if indic_ids else "api_metadata"
        try:
            frame = self.api_client().EcoInfoProGet(**kwargs)
            path = self.snapshot_root / "metadata" / f"{api_name}.parquet"
            output = self.write_frame(frame, path, "EcoInfoProGet", None)
            self.record_call("EcoInfoProGet", purpose, kwargs, output, path)
            return output
        except Exception as error:
            self.record_error("EcoInfoProGet", purpose, kwargs, error)
            if self.fail_fast:
                raise
            return pd.DataFrame()

    def discover_ids(
        self,
        metadata: pd.DataFrame,
        fallback: list[str],
    ) -> list[str]:
        if "indicID" not in metadata:
            return fallback
        eligible = metadata
        if "isList" in eligible:
            is_list = pd.to_numeric(eligible["isList"], errors="coerce")
            eligible = eligible.loc[is_list.ne(1)]
        ids = (
            eligible["indicID"]
            .astype("string")
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .tolist()
        )
        return unique_preserving_order(ids) or fallback

    def fetch_data(self, api_name: str, indic_ids: list[str]) -> None:
        for number, batch in enumerate(chunked(indic_ids, self.batch_size), start=1):
            kwargs = {
                "indicID": ",".join(batch),
                "beginDate": self.start_date,
                "endDate": self.end_date,
                "updateTime": "",
                "field": ",".join(DATA_FIELDS),
                "pandas": "1",
            }
            try:
                frame = getattr(self.api_client(), api_name)(**kwargs)
                path = (
                    self.snapshot_root
                    / "data"
                    / f"api={api_name}"
                    / f"part-{number:04d}.parquet"
                )
                output = self.write_frame(frame, path, api_name, number)
                self.record_call(api_name, "observations", kwargs, output, path)
            except Exception as error:
                self.record_error(api_name, "observations", kwargs, error)
                if self.fail_fast:
                    raise

    def run(self, mode: str, metadata_only: bool = False) -> Path:
        if mode not in {"sample", "metadata", "selected", "full"}:
            raise ValueError("mode 必须是 sample、metadata、selected 或 full")
        if mode == "selected" and self.selection is None:
            raise ValueError("selected 模式必须提供 --selection")
        if mode == "full" and not self.allow_all_indicators:
            raise ValueError(
                "full 会下载接口下所有指标；确认流量与范围后"
                "显式加 --allow-all-indicators"
            )
        self.ensure_snapshot_is_new()
        self.manifest["mode"] = mode
        self.manifest["metadata_only"] = metadata_only or mode == "metadata"

        try:
            groups = self.api_groups()
            if mode == "selected":
                assert self.selection is not None
                unknown = sorted(set(self.selection).difference(groups))
                if unknown:
                    raise ValueError(
                        "指标选择表包含未启用或不在清单的 API: "
                        + ", ".join(unknown)
                    )
                groups = {
                    api_name: groups[api_name] for api_name in self.selection
                }

            for api_name, rows in groups.items():
                metadata_names = unique_preserving_order(
                    row.metadata_api_name for row in rows
                )
                if len(metadata_names) != 1:
                    raise ValueError(
                        f"{api_name} 对应多个 metadata_api_name: "
                        f"{metadata_names}"
                    )
                metadata_api_name = metadata_names[0]
                sample_ids = unique_preserving_order(
                    row.sample_indic_id for row in rows
                )
                if mode == "sample":
                    requested_ids = sample_ids
                    metadata_ids: list[str] | None = sample_ids
                elif mode == "selected":
                    assert self.selection is not None
                    requested_ids = self.selection[api_name]
                    metadata_ids = requested_ids
                else:
                    requested_ids = []
                    metadata_ids = None

                metadata = self.fetch_metadata(
                    api_name, metadata_api_name, metadata_ids
                )
                if mode in {"metadata", "full"} and metadata.empty:
                    error = ValueError(
                        f"{api_name} 未返回元数据，不能继续全量发现"
                    )
                    self.record_error(
                        api_name,
                        "indicator_discovery",
                        {"dataApiName": metadata_api_name},
                        error,
                    )
                    if self.fail_fast:
                        raise error
                    continue

                if mode == "metadata":
                    continue
                indic_ids = (
                    self.discover_ids(metadata, sample_ids)
                    if mode == "full"
                    else requested_ids
                )
                if not indic_ids:
                    error = ValueError(f"{api_name} 没有可请求的指标代码")
                    self.record_error(
                        api_name, "indicator_selection", {}, error
                    )
                    if self.fail_fast:
                        raise error
                    continue
                if not metadata_only:
                    self.fetch_data(api_name, indic_ids)
        finally:
            self.manifest["completed_at_utc"] = utc_now().isoformat()
            self.manifest["summary"] = {
                "successful_calls": len(self.manifest["calls"]),
                "failed_calls": len(self.manifest["errors"]),
                "downloaded_rows": sum(
                    call["rows"] for call in self.manifest["calls"]
                ),
                "metadata_rows": sum(
                    call["rows"]
                    for call in self.manifest["calls"]
                    if call["api_name"] == "EcoInfoProGet"
                ),
                "observation_rows": sum(
                    call["rows"]
                    for call in self.manifest["calls"]
                    if call["purpose"] == "observations"
                ),
            }
            atomic_write_json(self.manifest, self.snapshot_root / "manifest.json")

        return self.snapshot_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载 UQER 宏观与行业景气指标，并保存可审计原始快照。"
    )
    parser.add_argument(
        "mode",
        choices=["sample", "metadata", "selected", "full"],
        help=(
            "sample=清单样例；metadata=仅盘点接口元数据；"
            "selected=仅下载审核清单；full=所有发现指标（高风险）。"
        ),
    )
    parser.add_argument("--start-date", required=True, help="YYYYMMDD")
    parser.add_argument(
        "--end-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="YYYYMMDD；默认今天。",
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--snapshot-id", default=default_snapshot_id())
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument(
        "--selection",
        type=Path,
        help=(
            "selected 模式的 CSV，必须包含 uqer_indic_id 和 "
            "uqer_api_name；可选 download_enabled。"
        ),
    )
    parser.add_argument(
        "--apis",
        help="可选，逗号分隔的 API 名；只下载指定接口。",
    )
    parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="也运行清单中因疑似错标而默认停用的行。",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="只下载指标元数据，不请求数值。",
    )
    parser.add_argument(
        "--allow-all-indicators",
        action="store_true",
        help="解锁 full 模式。使用前必须确认下载范围与流量。",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="任一接口失败时立即终止；默认记录错误后继续。",
    )
    return parser.parse_args()


def validate_dates(start_date: str, end_date: str) -> None:
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    if start > end:
        raise ValueError("start-date 不能晚于 end-date")


def main() -> int:
    args = parse_args()
    validate_dates(args.start_date, args.end_date)
    selected = set(args.apis.split(",")) if args.apis else None
    downloader = UqerIndustryDownloader(
        catalog_path=args.catalog,
        output_root=args.output_root,
        snapshot_id=args.snapshot_id,
        start_date=args.start_date,
        end_date=args.end_date,
        batch_size=args.batch_size,
        selected_apis=selected,
        selection_path=args.selection,
        include_disabled=args.include_disabled,
        fail_fast=args.fail_fast,
        allow_all_indicators=args.allow_all_indicators,
    )
    snapshot = downloader.run(args.mode, metadata_only=args.metadata_only)
    summary = downloader.manifest["summary"]
    print(
        f"完成：{summary['successful_calls']} 个成功请求，"
        f"{summary['failed_calls']} 个失败请求，"
        f"共 {summary['downloaded_rows']} 行。"
    )
    print(f"快照：{snapshot}")
    return 1 if summary["failed_calls"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
