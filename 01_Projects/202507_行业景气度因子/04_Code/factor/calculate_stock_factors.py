#!/usr/bin/env python3
"""从股票日行情中提取必要字段，计算项目已定义的动量类因子。

默认只读取 ``~/Desktop/InternData/StockData/processed/uqer_equity_daily_hfq``，
并将因子写入 ``~/Desktop/InternData/行业景气度项目Data/processed/stock_sentiment``。
脚本不会把原始行情复制到项目仓库，也不会默认覆盖已有结果。

支持 CSV / CSV.GZ / Parquet / Feather；通过列投影只加载日期、股票代码、
收盘价、最高价和最低价。如果自动识别不出字段，先运行 ``--schema-only``，
它只读文件头/元数据，不打印任何行情值。

与下载并行计算 2018–2020 阶段结果的示例：

    python calculate_stock_factors.py --start 2018-01-01 --end 2020-12-31 \
      --output-dir ~/Desktop/InternData/行业景气度项目Data/processed/stock_sentiment_through_2020 \
      --read-threads 2 --float32 --evaluate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import numpy as np
    import pandas as pd
except ImportError as exc:  # pragma: no cover - depends on local runtime
    raise SystemExit(
        "缺少依赖，请在项目虚拟环境中安装 pandas、numpy 和 pyarrow。"
    ) from exc


DEFAULT_INPUT_DIR = (
    Path.home()
    / "Desktop"
    / "InternData"
    / "StockData"
    / "processed"
    / "uqer_equity_daily_hfq"
)
DEFAULT_OUTPUT_DIR = (
    Path.home()
    / "Desktop"
    / "InternData"
    / "行业景气度项目Data"
    / "processed"
    / "stock_sentiment"
)
SUPPORTED_SUFFIXES = (".csv", ".csv.gz", ".parquet", ".pq", ".feather")
DEFAULT_WINDOWS = (5, 20, 60, 120, 252)
DEFAULT_LONG_WINDOWS = (60, 120, 252)
PIPELINE_VERSION = "1.1.0"
SCRIPT_PATH = Path(__file__).resolve()
FACTOR_DEFINITION_DOC = (
    SCRIPT_PATH.parents[2] / "02_Factors" / "02_动量因子" / "因子构建.md"
)

# 别名只用于字段自动识别；显式 --*-column 参数始终优先。
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": (
        "date",
        "trade_date",
        "trading_date",
        "datetime",
        "trade_dt",
        "交易日期",
        "日期",
        "时间",
    ),
    "symbol": (
        "symbol",
        "ticker",
        "code",
        "stock_code",
        "sec_code",
        "ts_code",
        "wind_code",
        "股票代码",
        "证券代码",
        "代码",
    ),
    # 复权价优先，避免分红、拆合股伪造动量。
    "close": (
        "adj_close",
        "adjusted_close",
        "close_hfq",
        "hfq_close",
        "close_qfq",
        "qfq_close",
        "后复权收盘价",
        "前复权收盘价",
        "close",
        "close_price",
        "收盘价",
        "收盘",
    ),
    "high": (
        "adj_high",
        "adjusted_high",
        "high_hfq",
        "hfq_high",
        "high_qfq",
        "qfq_high",
        "后复权最高价",
        "前复权最高价",
        "high",
        "high_price",
        "最高价",
        "最高",
    ),
    "low": (
        "adj_low",
        "adjusted_low",
        "low_hfq",
        "hfq_low",
        "low_qfq",
        "qfq_low",
        "后复权最低价",
        "前复权最低价",
        "low",
        "low_price",
        "最低价",
        "最低",
    ),
    "is_open": ("is_open", "isopen", "trade_status", "是否交易", "停复牌状态"),
}


class FactorPipelineError(RuntimeError):
    """可预期的数据或参数错误。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "提取股票日行情必要列，计算动量、截面排名、z-score、"
            "Rank Momentum、Smooth Momentum 和 Position Factor。"
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--glob",
        default="**/*",
        help="输入目录下的 glob，默认递归发现所有支持的文件。",
    )
    parser.add_argument("--date-column", help="日期列名；不填则自动识别。")
    parser.add_argument("--symbol-column", help="股票代码列名；不填则自动识别。")
    parser.add_argument("--close-column", help="收盘价列名，建议显式指定复权价。")
    parser.add_argument("--high-column", help="最高价列名。")
    parser.add_argument("--low-column", help="最低价列名。")
    parser.add_argument("--is-open-column", help="是否正常交易列名。")
    parser.add_argument(
        "--include-suspended",
        action="store_true",
        help="保留 is_open!=1 的记录；默认剔除停牌/未交易行。",
    )
    parser.add_argument(
        "--skip-position",
        action="store_true",
        help="数据没有高/低价时，跳过 Position Factor。",
    )
    parser.add_argument(
        "--start",
        help="可选输出起始日期，YYYY-MM-DD；更早历史仍用于窗口预热。",
    )
    parser.add_argument("--end", help="可选输出结束日期，YYYY-MM-DD。")
    parser.add_argument(
        "--windows",
        nargs="+",
        type=int,
        default=list(DEFAULT_WINDOWS),
        metavar="N",
        help="因子窗口，默认 5 20 60 120 252。",
    )
    parser.add_argument(
        "--long-windows",
        nargs="*",
        type=int,
        default=list(DEFAULT_LONG_WINDOWS),
        metavar="N",
        help="需跳过近期的长周期动量窗口。",
    )
    parser.add_argument(
        "--skip-recent",
        type=int,
        default=20,
        help="长周期动量跳过的最近交易观测数，默认 20。",
    )
    parser.add_argument(
        "--signal-lag",
        type=int,
        default=0,
        help=(
            "将所有因子按股票向后移动 N 个交易观测。默认 0；"
            "回测应将 t 日收盘后因子对应到 t+1 收益。"
        ),
    )
    parser.add_argument(
        "--duplicate-policy",
        choices=("error", "last"),
        default="error",
        help="同一股票同日重复时终止，或保留最后一条。",
    )
    parser.add_argument(
        "--symbol-width",
        type=int,
        help="对纯数字代码左补零到指定长度，A 股通常可设为 6。",
    )
    parser.add_argument(
        "--encoding", default="utf-8", help="CSV 编码，默认 utf-8。"
    )
    parser.add_argument(
        "--csv-engine",
        choices=("pyarrow", "c"),
        default="pyarrow",
        help="CSV 读取引擎，默认 pyarrow（更快）。",
    )
    parser.add_argument(
        "--read-threads",
        type=int,
        help="限制 Arrow 读取线程数；与下载并行时建议设为 2。",
    )
    parser.add_argument(
        "--price-adjustment",
        choices=("auto", "hfq", "qfq", "raw"),
        default="auto",
        help="价格复权口径；默认从路径/列名判断。",
    )
    parser.add_argument(
        "--output-format", choices=("parquet", "csv"), default="parquet"
    )
    parser.add_argument(
        "--include-price-columns",
        action="store_true",
        help="在输出中保留 close/high/low；默认只保留主键与因子。",
    )
    parser.add_argument(
        "--include-daily-return",
        action="store_true",
        help="在输出中保留计算中产生的日收益率。",
    )
    parser.add_argument(
        "--float32",
        action="store_true",
        help="将数值列压缩为 float32，可显著降低结果体积。",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="同时计算因子与未来收益的日度 Spearman IC 及汇总。",
    )
    parser.add_argument(
        "--forward-horizons",
        nargs="+",
        type=int,
        default=[1, 5, 20],
        metavar="N",
        help="IC 评价的未来收益期限，默认 1 5 20。",
    )
    parser.add_argument(
        "--min-cross-section",
        type=int,
        default=30,
        help="单日 IC 所需的最少有效股票数，默认 30。",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="只读取文件头/元数据并输出字段诊断，不读取行情值。",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="明确允许覆盖已有因子文件。"
    )
    return parser.parse_args()


def file_kind(path: Path) -> str | None:
    lower_name = path.name.lower()
    if lower_name.endswith(".csv.gz"):
        return "csv"
    if lower_name.endswith(".csv"):
        return "csv"
    if lower_name.endswith((".parquet", ".pq")):
        return "parquet"
    if lower_name.endswith(".feather"):
        return "feather"
    return None


def discover_files(input_dir: Path, pattern: str) -> list[Path]:
    if not input_dir.exists():
        raise FactorPipelineError(f"输入目录不存在: {input_dir}")
    if not input_dir.is_dir():
        raise FactorPipelineError(f"输入路径不是目录: {input_dir}")
    files = sorted(
        path for path in input_dir.glob(pattern) if path.is_file() and file_kind(path)
    )
    if not files:
        raise FactorPipelineError(
            f"未在 {input_dir} 中发现 {SUPPORTED_SUFFIXES} 文件。"
        )
    return files


def prune_daily_files_after_end(
    files: list[Path], end: str | None
) -> tuple[list[Path], int]:
    """利用 YYYYMMDD.parquet 日文件名预先剪枝，避免读取输出期间之后的文件。"""
    if not end:
        return files, 0
    end_date = pd.Timestamp(end).normalize()
    kept: list[Path] = []
    pruned = 0
    for path in files:
        match = re.fullmatch(r"(\d{8})", path.stem)
        if match and pd.to_datetime(
            match.group(1), format="%Y%m%d"
        ) > end_date:
            pruned += 1
        else:
            kept.append(path)
    if not kept:
        raise FactorPipelineError("end 日期剪枝后没有可读取的日行情文件。")
    return kept, pruned


def read_schema(path: Path, encoding: str) -> list[str]:
    kind = file_kind(path)
    if kind == "csv":
        # nrows=0 只解析表头，不读取行情记录。
        return [str(column) for column in pd.read_csv(path, nrows=0, encoding=encoding)]
    try:
        import pyarrow as pa
        import pyarrow.ipc as ipc
        import pyarrow.parquet as parquet
    except ImportError as exc:  # pragma: no cover - depends on local runtime
        raise FactorPipelineError("Parquet/Feather 需要 pyarrow。") from exc
    if kind == "parquet":
        return [str(column) for column in parquet.ParquetFile(path).schema_arrow.names]
    if kind == "feather":
        # Feather V2 是 Arrow IPC file；只打开 schema，不物化数据列。
        with pa.memory_map(str(path), "r") as source:
            return [str(column) for column in ipc.open_file(source).schema.names]
    raise FactorPipelineError(f"不支持的文件: {path}")


def normalise_label(label: str) -> str:
    return "".join(char for char in str(label).strip().casefold() if char not in " _-./")


def resolve_one_column(
    columns: Iterable[str], role: str, explicit: str | None, required: bool
) -> str | None:
    columns = list(columns)
    normalised: dict[str, list[str]] = {}
    for column in columns:
        normalised.setdefault(normalise_label(column), []).append(column)

    if explicit:
        if explicit in columns:
            return explicit
        matches = normalised.get(normalise_label(explicit), [])
        if len(matches) == 1:
            return matches[0]
        raise FactorPipelineError(f"指定的 {role} 列不存在: {explicit}")

    for alias in COLUMN_ALIASES[role]:
        matches = normalised.get(normalise_label(alias), [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise FactorPipelineError(
                f"{role} 列自动识别存在歧义，请用 --{role}-column 显式指定。"
            )
    if required:
        raise FactorPipelineError(
            f"无法自动识别 {role} 列，请运行 --schema-only 后显式指定。"
        )
    return None


def resolve_columns(
    columns: Iterable[str], args: argparse.Namespace
) -> dict[str, str]:
    explicit = {
        "date": args.date_column,
        "symbol": args.symbol_column,
        "close": args.close_column,
        "high": args.high_column,
        "low": args.low_column,
        "is_open": args.is_open_column,
    }
    mapping: dict[str, str] = {}
    for role in ("date", "symbol", "close"):
        value = resolve_one_column(columns, role, explicit[role], required=True)
        assert value is not None
        mapping[role] = value
    for role in ("high", "low"):
        value = resolve_one_column(
            columns, role, explicit[role], required=not args.skip_position
        )
        if value is not None:
            mapping[role] = value
    is_open = resolve_one_column(
        columns, "is_open", explicit["is_open"], required=False
    )
    if is_open is not None:
        mapping["is_open"] = is_open
    if not args.skip_position and {"high", "low"}.difference(mapping):
        raise FactorPipelineError(
            "Position Factor 需要 high 和 low；请指定列名或使用 --skip-position。"
        )
    if len(set(mapping.values())) != len(mapping):
        raise FactorPipelineError(
            "日期、代码、收盘价和高低价不能映射到同一个源字段。"
        )
    return mapping


def schema_report(files: list[Path], input_dir: Path, encoding: str) -> dict[str, Any]:
    grouped: Counter[tuple[str, ...]] = Counter()
    examples: dict[tuple[str, ...], str] = {}
    formats: Counter[str] = Counter()
    failures: list[dict[str, str]] = []
    for path in files:
        try:
            columns = tuple(read_schema(path, encoding))
            grouped[columns] += 1
            examples.setdefault(columns, str(path.relative_to(input_dir)))
            formats[file_kind(path) or "unknown"] += 1
        except (OSError, ValueError, UnicodeError, FactorPipelineError) as exc:
            failures.append(
                {"file": str(path.relative_to(input_dir)), "error": str(exc)}
            )
    schemas = [
        {"file_count": count, "example_file": examples[columns], "columns": columns}
        for columns, count in grouped.most_common()
    ]
    return {
        "input_dir": str(input_dir.resolve()),
        "file_count": len(files),
        "formats": dict(formats),
        "distinct_schema_count": len(grouped),
        "schemas": schemas,
        "schema_failures": failures[:20],
        "note": "本报告只读取表头或文件元数据，不包含任何行情值。",
    }


def validate_args(args: argparse.Namespace) -> None:
    windows = sorted(set(args.windows))
    long_windows = sorted(set(args.long_windows))
    if not windows or any(window <= 0 for window in windows):
        raise FactorPipelineError("windows 必须是正整数。")
    if set(long_windows).difference(windows):
        raise FactorPipelineError("long-windows 必须是 windows 的子集。")
    if args.skip_recent < 0 or args.signal_lag < 0:
        raise FactorPipelineError("skip-recent 和 signal-lag 不能为负数。")
    if any(window <= args.skip_recent for window in long_windows):
        raise FactorPipelineError("长周期窗口必须大于 skip-recent。")
    if args.symbol_width is not None and args.symbol_width <= 0:
        raise FactorPipelineError("symbol-width 必须是正整数。")
    if args.read_threads is not None and args.read_threads <= 0:
        raise FactorPipelineError("read-threads 必须是正整数。")
    if args.min_cross_section < 2:
        raise FactorPipelineError("min-cross-section 至少为 2。")
    if not args.forward_horizons or any(
        horizon <= 0 for horizon in args.forward_horizons
    ):
        raise FactorPipelineError("forward-horizons 必须是正整数。")
    if args.start and args.end and pd.Timestamp(args.start) > pd.Timestamp(args.end):
        raise FactorPipelineError("start 不能晚于 end。")
    args.windows = windows
    args.long_windows = long_windows
    args.forward_horizons = sorted(set(args.forward_horizons))


def validate_storage_boundary(input_dir: Path, output_dir: Path) -> None:
    input_resolved = input_dir.resolve()
    output_resolved = output_dir.resolve()
    if output_resolved == input_resolved or output_resolved.is_relative_to(
        input_resolved
    ) or input_resolved.is_relative_to(output_resolved):
        raise FactorPipelineError(
            "输入与输出目录不能相同或互为上下级，请使用两个隔离的同级目录。"
        )


def load_one_file(
    path: Path, mapping: dict[str, str], args: argparse.Namespace
) -> pd.DataFrame:
    source_columns = list(dict.fromkeys(mapping.values()))
    kind = file_kind(path)
    if kind == "csv":
        if args.csv_engine == "pyarrow":
            try:
                import pyarrow as pa
                import pyarrow.csv as arrow_csv
            except ImportError as exc:  # pragma: no cover - runtime dependent
                raise FactorPipelineError("pyarrow CSV 引擎需要 pyarrow。") from exc
            if args.read_threads is not None:
                pa.set_cpu_count(args.read_threads)
            read_options = arrow_csv.ReadOptions(
                use_threads=True, encoding=args.encoding
            )
            convert_options = arrow_csv.ConvertOptions(
                include_columns=source_columns,
                column_types={mapping["symbol"]: pa.string()},
                strings_can_be_null=True,
            )
            with pa.input_stream(str(path), compression="detect") as source:
                table = arrow_csv.read_csv(
                    source,
                    read_options=read_options,
                    convert_options=convert_options,
                )
            frame = table.to_pandas()
        else:
            frame = pd.read_csv(
                path,
                usecols=source_columns,
                encoding=args.encoding,
                engine="c",
                dtype={mapping["symbol"]: "string"},
                low_memory=False,
                memory_map=not path.name.lower().endswith(".gz"),
            )
    elif kind == "parquet":
        frame = pd.read_parquet(path, columns=source_columns, engine="pyarrow")
    elif kind == "feather":
        frame = pd.read_feather(path, columns=source_columns)
    else:  # pragma: no cover - discovery already filters this
        raise FactorPipelineError(f"不支持的文件: {path}")
    reverse_mapping = {source: role for role, source in mapping.items()}
    return frame.rename(columns=reverse_mapping)[list(mapping)]


def load_parquet_batch(
    files: list[Path], mapping: dict[str, str], read_threads: int | None
) -> pd.DataFrame:
    """用一次 Arrow Dataset 扫描读取大量日 Parquet，避免逐文件开启开销。"""
    try:
        import pyarrow as pa
        import pyarrow.dataset as arrow_dataset
    except ImportError as exc:  # pragma: no cover - runtime dependent
        raise FactorPipelineError("Parquet 批量读取需要 pyarrow。") from exc
    if read_threads is not None:
        pa.set_cpu_count(read_threads)
    source_columns = list(dict.fromkeys(mapping.values()))
    dataset = arrow_dataset.dataset(
        [str(path) for path in files], format="parquet"
    )
    table = dataset.scanner(columns=source_columns, use_threads=True).to_table()
    frame = table.to_pandas()
    reverse_mapping = {source: role for role, source in mapping.items()}
    return frame.rename(columns=reverse_mapping)[list(mapping)]


def parse_dates(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    compact_text = text.str.replace(r"\.0$", "", regex=True)
    compact = compact_text.str.fullmatch(r"\d{8}", na=False)
    if bool(compact.all()):
        parsed = pd.to_datetime(compact_text, format="%Y%m%d", errors="coerce")
    else:
        parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.normalize()


def load_market_data(
    files: list[Path], input_dir: Path, args: argparse.Namespace
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    schema_mappings: Counter[tuple[tuple[str, str], ...]] = Counter()
    total_bytes = 0
    metadata_digest = hashlib.sha256()
    for path in files:
        stat = path.stat()
        total_bytes += stat.st_size
        identity = (
            f"{path.relative_to(input_dir)}\0{stat.st_size}\0{stat.st_mtime_ns}\n"
        )
        metadata_digest.update(identity.encode("utf-8"))

    all_parquet = all(file_kind(path) == "parquet" for path in files)
    if all_parquet:
        columns = read_schema(files[0], args.encoding)
        mapping = resolve_columns(columns, args)
        schema_mappings[tuple(sorted(mapping.items()))] = len(files)
        market = load_parquet_batch(files, mapping, args.read_threads)
        loading_mode = "pyarrow_dataset_batch"
        print(f"已批量加载 {len(files)} 个 Parquet 文件。", file=sys.stderr)
    else:
        for index, path in enumerate(files, start=1):
            columns = read_schema(path, args.encoding)
            mapping = resolve_columns(columns, args)
            schema_mappings[tuple(sorted(mapping.items()))] += 1
            frames.append(load_one_file(path, mapping, args))
            if index == 1 or index % 100 == 0 or index == len(files):
                print(f"已加载 {index}/{len(files)} 个文件。", file=sys.stderr)
        market = pd.concat(frames, ignore_index=True, copy=False)
        del frames
        loading_mode = "per_file_mixed_format"
    raw_rows = len(market)
    market["date"] = parse_dates(market["date"])
    market["symbol"] = market["symbol"].astype("string").str.strip()
    invalid_date = int(market["date"].isna().sum())
    invalid_symbol = int(
        (market["symbol"].isna() | market["symbol"].eq("")).sum()
    )
    if invalid_date or invalid_symbol:
        raise FactorPipelineError(
            f"主键校验失败：无效日期 {invalid_date} 行，无效股票代码 {invalid_symbol} 行。"
        )
    if args.symbol_width:
        numeric_symbol = market["symbol"].str.fullmatch(r"\d+", na=False)
        market.loc[numeric_symbol, "symbol"] = market.loc[
            numeric_symbol, "symbol"
        ].str.zfill(args.symbol_width)

    suspended_rows_removed = 0
    if "is_open" in market and not args.include_suspended:
        open_status = pd.to_numeric(market["is_open"], errors="coerce")
        suspended_rows_removed = int(open_status.ne(1).sum())
        market = market.loc[open_status.eq(1)].copy()

    if args.end:
        market = market.loc[market["date"] <= pd.Timestamp(args.end)]
    if market.empty:
        raise FactorPipelineError("日期筛选后没有数据。")

    price_columns = [column for column in ("close", "high", "low") if column in market]
    for column in price_columns:
        market[column] = pd.to_numeric(market[column], errors="coerce")
    nonpositive_close = int(market["close"].le(0).fillna(False).sum())
    market.loc[market["close"] <= 0, "close"] = np.nan
    for column in ("high", "low"):
        if column in market:
            market.loc[market[column] <= 0, column] = np.nan
    if args.float32:
        market[price_columns] = market[price_columns].astype("float32")

    market = market.sort_values(["symbol", "date"], kind="mergesort")
    duplicate_mask = market.duplicated(["symbol", "date"], keep=False)
    duplicate_rows = int(duplicate_mask.sum())
    duplicate_keys = int(
        market.loc[duplicate_mask, ["symbol", "date"]].drop_duplicates().shape[0]
    )
    if duplicate_rows:
        if args.duplicate_policy == "error":
            raise FactorPipelineError(
                f"发现 {duplicate_keys} 个重复 symbol×date 主键（{duplicate_rows} 行）；"
                "请清理数据，或明确使用 --duplicate-policy last。"
            )
        market = market.drop_duplicates(["symbol", "date"], keep="last")
    market = market.reset_index(drop=True)

    global_dates = pd.Index(market["date"].drop_duplicates().sort_values())
    date_number = market["date"].map(
        pd.Series(np.arange(len(global_dates)), index=global_dates)
    )
    calendar_coverage = date_number.groupby(
        market["symbol"], sort=False, observed=True
    ).agg(["count", "min", "max"])
    internal_gaps = (
        calendar_coverage["max"]
        - calendar_coverage["min"]
        + 1
        - calendar_coverage["count"]
    ).clip(lower=0)
    high_below_low = 0
    close_outside_range = 0
    if {"high", "low"}.issubset(market.columns):
        high_below_low = int((market["high"] < market["low"]).fillna(False).sum())
        close_outside_range = int(
            (
                (market["close"] > market["high"])
                | (market["close"] < market["low"])
            )
            .fillna(False)
            .sum()
        )

    summary = {
        "input_dir": str(input_dir.resolve()),
        "input_file_count": len(files),
        "input_total_bytes": total_bytes,
        "input_metadata_sha256": metadata_digest.hexdigest(),
        "input_fingerprint_note": "基于相对路径、文件大小和修改时间；未逐字节读取大型原始文件。",
        "input_formats": dict(Counter(file_kind(path) for path in files)),
        "loading_mode": loading_mode,
        "distinct_column_mappings": len(schema_mappings),
        "column_mappings": [
            {"file_count": count, "mapping": dict(mapping)}
            for mapping, count in schema_mappings.most_common()
        ],
        "raw_rows": raw_rows,
        "rows_after_filter_and_deduplication": len(market),
        "symbols": int(market["symbol"].nunique()),
        "dates": int(market["date"].nunique()),
        "date_start": market["date"].min().strftime("%Y-%m-%d"),
        "date_end": market["date"].max().strftime("%Y-%m-%d"),
        "duplicate_rows": duplicate_rows,
        "duplicate_keys": duplicate_keys,
        "symbols_with_internal_calendar_gaps": int(internal_gaps.gt(0).sum()),
        "internal_calendar_gap_rows": int(internal_gaps.sum()),
        "nonpositive_close_converted_to_missing": nonpositive_close,
        "suspended_or_nontrading_rows_removed": suspended_rows_removed,
        "high_below_low_rows": high_below_low,
        "close_outside_high_low_rows": close_outside_range,
        "missing_ratio": {
            column: round(float(market[column].isna().mean()), 8)
            for column in price_columns
        },
    }
    return market, summary


def grouped_rolling_mean(
    series: pd.Series, symbols: pd.Series, window: int
) -> pd.Series:
    return (
        series.groupby(symbols, sort=False, observed=True)
        .rolling(window, min_periods=window)
        .mean()
        .reset_index(level=0, drop=True)
        .reindex(series.index)
    )


def grouped_rolling_sum(
    series: pd.Series, symbols: pd.Series, window: int
) -> pd.Series:
    return (
        series.groupby(symbols, sort=False, observed=True)
        .rolling(window, min_periods=window)
        .sum()
        .reset_index(level=0, drop=True)
        .reindex(series.index)
    )


def grouped_rolling_extreme(
    series: pd.Series, symbols: pd.Series, window: int, operation: str
) -> pd.Series:
    rolling = series.groupby(symbols, sort=False, observed=True).rolling(
        window, min_periods=window
    )
    values = rolling.max() if operation == "max" else rolling.min()
    return values.reset_index(level=0, drop=True).reindex(series.index)


def finite(series: pd.Series) -> pd.Series:
    return series.replace([np.inf, -np.inf], np.nan)


def factor_columns(frame: pd.DataFrame) -> list[str]:
    excluded = {"date", "symbol", "close", "high", "low", "daily_return"}
    return [column for column in frame.columns if column not in excluded]


def calculate_factors(market: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    symbols = market["symbol"]
    dates = market["date"]
    close = market["close"]
    grouped_close = close.groupby(symbols, sort=False, observed=True)
    daily_return = finite(grouped_close.pct_change(fill_method=None))

    output_columns: dict[str, pd.Series] = {}
    if args.include_daily_return:
        output_columns["daily_return"] = daily_return

    daily_rank = daily_return.groupby(dates, sort=False).rank(
        method="average", ascending=True
    )
    daily_n = daily_return.groupby(dates, sort=False).transform("count")
    denominator_squared = ((daily_n - 1) * (daily_n + 1) / 12.0).where(
        daily_n > 1
    )
    denominator = np.sqrt(denominator_squared)
    wright_rank = finite((daily_rank - (daily_n + 1) / 2.0) / denominator)

    long_windows = set(args.long_windows)
    for window in args.windows:
        if window in long_windows:
            numerator = grouped_close.shift(args.skip_recent)
            momentum = finite(numerator / grouped_close.shift(window) - 1.0)
        else:
            momentum = finite(close / grouped_close.shift(window) - 1.0)

        factor_name = f"momentum_{window}d"
        output_columns[factor_name] = momentum
        output_columns[f"momentum_rank_pct_{window}d"] = momentum.groupby(
            dates, sort=False
        ).rank(method="average", pct=True)
        cross_mean = momentum.groupby(dates, sort=False).transform("mean")
        cross_std = momentum.groupby(dates, sort=False).transform("std", ddof=0)
        output_columns[f"momentum_z_{window}d"] = finite(
            (momentum - cross_mean) / cross_std
        )
        output_columns[f"rank_momentum_{window}d"] = grouped_rolling_mean(
            wright_rank, symbols, window
        )

        cumulative_return = finite(close / grouped_close.shift(window) - 1.0)
        absolute_path = grouped_rolling_sum(daily_return.abs(), symbols, window)
        output_columns[f"smooth_momentum_{window}d"] = finite(
            cumulative_return / absolute_path
        )

        if not args.skip_position:
            rolling_high = grouped_rolling_extreme(
                market["high"], symbols, window, "max"
            )
            rolling_low = grouped_rolling_extreme(
                market["low"], symbols, window, "min"
            )
            output_columns[f"position_{window}d"] = finite(
                (close - rolling_low) / (rolling_high - rolling_low)
            )
        print(f"已计算 {window} 日因子。", file=sys.stderr)

    factors = pd.DataFrame(output_columns, index=market.index)
    if args.signal_lag:
        factors = factors.groupby(symbols, sort=False, observed=True).shift(
            args.signal_lag
        )

    keys_and_prices = ["date", "symbol"]
    if args.include_price_columns:
        keys_and_prices.extend(
            column for column in ("close", "high", "low") if column in market
        )
    output = pd.concat([market[keys_and_prices], factors], axis=1)
    numeric_columns = output.select_dtypes(include=["number"]).columns
    if args.float32:
        output[numeric_columns] = output[numeric_columns].astype("float32")
    output = output.sort_values(["date", "symbol"], kind="mergesort")
    if args.start:
        output = output.loc[output["date"] >= pd.Timestamp(args.start)]
    if output.empty:
        raise FactorPipelineError("输出日期范围内没有数据。")
    return output.reset_index(drop=True)


def evaluate_ic(
    factors: pd.DataFrame, market: pd.DataFrame, args: argparse.Namespace
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """计算每日截面 Spearman IC，因子日 t 对应 t 之后的复权收益。"""
    targets = market[["date", "symbol"]].copy()
    grouped_close = market["close"].groupby(
        market["symbol"], sort=False, observed=True
    )
    for horizon in args.forward_horizons:
        targets[f"forward_return_{horizon}d"] = finite(
            grouped_close.shift(-horizon) / market["close"] - 1.0
        )
    targets = targets.sort_values(["date", "symbol"], kind="mergesort")
    if args.start:
        targets = targets.loc[targets["date"] >= pd.Timestamp(args.start)]
    targets = targets.reset_index(drop=True)
    if not factors[["date", "symbol"]].equals(targets[["date", "symbol"]]):
        raise FactorPipelineError("IC 评价时因子与未来收益主键未对齐。")

    dates = factors["date"]
    daily_ic: dict[str, pd.Series] = {}
    summary_rows: list[dict[str, Any]] = []
    ranked_targets = {
        horizon: targets[f"forward_return_{horizon}d"]
        .groupby(dates, sort=False)
        .rank(method="average")
        for horizon in args.forward_horizons
    }
    for column in factor_columns(factors):
        factor_rank = factors[column].groupby(dates, sort=False).rank(
            method="average"
        )
        for horizon, target_rank in ranked_targets.items():
            valid = factor_rank.notna() & target_rank.notna()
            count = valid.groupby(dates, sort=False).sum()
            ic = factor_rank.where(valid).groupby(dates, sort=False).corr(
                target_rank.where(valid)
            )
            ic = ic.where(count >= args.min_cross_section)
            ic_name = f"{column}__fwd_{horizon}d"
            daily_ic[ic_name] = ic
            valid_ic = ic.dropna()
            observations = len(valid_ic)
            mean_ic = float(valid_ic.mean()) if observations else math.nan
            std_ic = float(valid_ic.std(ddof=1)) if observations > 1 else math.nan
            summary_rows.append(
                {
                    "factor": column,
                    "forward_horizon_days": horizon,
                    "ic_days": observations,
                    "ic_mean": mean_ic,
                    "ic_std": std_ic,
                    "icir_annualized": (
                        mean_ic / std_ic * np.sqrt(252.0)
                        if observations > 1 and std_ic > 0
                        else math.nan
                    ),
                    "t_stat": (
                        mean_ic / (std_ic / np.sqrt(observations))
                        if observations > 1 and std_ic > 0
                        else math.nan
                    ),
                    "positive_ratio": (
                        float(valid_ic.gt(0).mean()) if observations else math.nan
                    ),
                }
            )
        print(f"已计算 {column} 的 IC。", file=sys.stderr)

    daily = pd.DataFrame(daily_ic)
    daily.index.name = "date"
    daily = daily.reset_index()
    summary = pd.DataFrame(summary_rows)
    return daily, summary


def build_manifest(
    factors: pd.DataFrame,
    input_summary: dict[str, Any],
    args: argparse.Namespace,
    output_file: Path,
) -> dict[str, Any]:
    factor_column_names = factor_columns(factors)
    close_column = args.close_column or "auto_detected"
    mapped_close_columns = sorted(
        {
            item["mapping"]["close"]
            for item in input_summary.get("column_mappings", [])
            if "close" in item["mapping"]
        }
    )
    effective_adjustment = args.price_adjustment
    if effective_adjustment == "auto":
        input_label = normalise_label(input_summary.get("input_dir", ""))
        if "hfq" in input_label or "后复权" in input_label:
            effective_adjustment = "hfq"
        elif "qfq" in input_label or "前复权" in input_label:
            effective_adjustment = "qfq"
    adjustment_warning = None
    if effective_adjustment == "auto" and any(
        not any(
            marker in normalise_label(column)
            for marker in ("adj", "hfq", "qfq", "复权")
        )
        for column in mapped_close_columns
    ):
        adjustment_warning = (
            "实际使用的部分收盘价列名未显示复权口径；请人工确认，避免除权除息伪造动量。"
        )
    price_consistency_warning = None
    adjustment_markers = {
        "hfq": ("hfq", "后复权"),
        "qfq": ("qfq", "前复权"),
        "adjusted": ("adj", "adjusted", "复权"),
    }

    def adjustment_tag(column: str) -> str:
        label = normalise_label(column)
        for tag, markers in adjustment_markers.items():
            if any(marker in label for marker in markers):
                return tag
        return "unspecified"

    for item in input_summary.get("column_mappings", []):
        mapping = item["mapping"]
        tags = {
            role: adjustment_tag(mapping[role])
            for role in ("close", "high", "low")
            if role in mapping
        }
        known_tags = {tag for tag in tags.values() if tag != "unspecified"}
        if effective_adjustment == "auto" and (
            len(known_tags) > 1 or (known_tags and "unspecified" in tags.values())
        ):
            price_consistency_warning = (
                "close/high/low 的列名显示复权口径可能不一致；"
                "Position Factor 运行前请人工确认三列口径相同。"
            )
            break
    data_quality_warnings: list[str] = []
    if input_summary.get("symbols_with_internal_calendar_gaps", 0):
        data_quality_warnings.append(
            "部分股票在自身首尾日期之间存在缺失的全市场交易日；"
            "本脚本不填充价格，窗口按该股票实际行情观测计数。"
        )
    if input_summary.get("high_below_low_rows", 0) or input_summary.get(
        "close_outside_high_low_rows", 0
    ):
        data_quality_warnings.append(
            "发现 high<low 或 close 位于 [low, high] 之外的记录；"
            "请在使用 Position Factor 前检查质量报告中的计数。"
        )
    return {
        "pipeline_version": PIPELINE_VERSION,
        "factor_definition_document": str(FACTOR_DEFINITION_DOC),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_file": str(output_file.resolve()),
        "rows": len(factors),
        "factor_count": len(factor_column_names),
        "factor_columns": factor_column_names,
        "factor_missing_ratio": {
            column: round(float(factors[column].isna().mean()), 8)
            for column in factor_column_names
        },
        "parameters": {
            "windows": args.windows,
            "long_windows": args.long_windows,
            "skip_recent": args.skip_recent,
            "signal_lag": args.signal_lag,
            "duplicate_policy": args.duplicate_policy,
            "close_column_argument": close_column,
            "high_column_argument": args.high_column or "auto_detected",
            "low_column_argument": args.low_column or "auto_detected",
            "position_factor_skipped": args.skip_position,
            "suspended_rows_included": args.include_suspended,
            "float_dtype": "float32" if args.float32 else "float64",
            "price_adjustment_argument": args.price_adjustment,
            "price_adjustment_effective": effective_adjustment,
            "evaluation_enabled": args.evaluate,
            "forward_horizons": args.forward_horizons if args.evaluate else [],
            "min_cross_section": args.min_cross_section if args.evaluate else None,
        },
        "semantics": {
            "window_unit": "每只股票按日期排序后的有效行情观测（通常为交易日）",
            "availability": (
                "signal_lag=0 时，t 日因子在 t 日收盘价可用后才可观测；"
                "回测不得用于 t 日已经完成的交易。"
            ),
            "missing_values": "不填充价格；窗口不足或分母为零时因子为空。",
            "cross_section": "按 date 在当日全部可用股票中计算排名和总体标准差 z-score。",
            "evaluation_scope": (
                "IC 为全市场可交易样本的初步截面评价；未施加历史股票池、"
                "行业/市值中性化、流动性筛选或交易成本，不应当作最终验证结论。"
            ),
        },
        "warnings": [
            warning
            for warning in (adjustment_warning, price_consistency_warning)
            if warning
        ]
        + data_quality_warnings,
        "input_summary": input_summary,
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_outputs(
    factors: pd.DataFrame,
    input_summary: dict[str, Any],
    args: argparse.Namespace,
    ic_daily: pd.DataFrame | None = None,
    ic_summary: pd.DataFrame | None = None,
) -> tuple[Path, Path, Path | None, Path | None]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    extension = "parquet" if args.output_format == "parquet" else "csv"
    output_file = args.output_dir / f"stock_factors.{extension}"
    manifest_file = args.output_dir / "stock_factor_manifest.json"
    ic_daily_file = args.output_dir / "stock_factor_ic_daily.parquet" if args.evaluate else None
    ic_summary_file = args.output_dir / "stock_factor_ic_summary.csv" if args.evaluate else None
    targets = [output_file, manifest_file]
    targets.extend(path for path in (ic_daily_file, ic_summary_file) if path)
    existing = [path for path in targets if path.exists()]
    if not args.overwrite and existing:
        raise FactorPipelineError(
            f"输出已存在: {existing[0]}；"
            "请更换 --output-dir，或明确使用 --overwrite。"
        )

    temporary = output_file.with_name(
        f".{output_file.stem}.{os.getpid()}.tmp.{extension}"
    )
    try:
        if args.output_format == "parquet":
            factors.to_parquet(
                temporary, index=False, engine="pyarrow", compression="zstd"
            )
        else:
            factors.to_csv(
                temporary,
                index=False,
                encoding="utf-8-sig",
                date_format="%Y-%m-%d",
            )
        temporary.replace(output_file)
    finally:
        if temporary.exists():
            temporary.unlink()

    if args.evaluate:
        if ic_daily is None or ic_summary is None:
            raise FactorPipelineError("已启用 evaluate，但 IC 结果未生成。")
        assert ic_daily_file is not None and ic_summary_file is not None
        temporary_ic = ic_daily_file.with_name(
            f".{ic_daily_file.stem}.{os.getpid()}.tmp.parquet"
        )
        temporary_summary = ic_summary_file.with_name(
            f".{ic_summary_file.stem}.{os.getpid()}.tmp.csv"
        )
        try:
            ic_daily.to_parquet(
                temporary_ic, index=False, engine="pyarrow", compression="zstd"
            )
            ic_summary.to_csv(temporary_summary, index=False, encoding="utf-8-sig")
            temporary_ic.replace(ic_daily_file)
            temporary_summary.replace(ic_summary_file)
        finally:
            if temporary_ic.exists():
                temporary_ic.unlink()
            if temporary_summary.exists():
                temporary_summary.unlink()

    manifest = build_manifest(factors, input_summary, args, output_file)
    if args.evaluate:
        manifest["evaluation_outputs"] = {
            "daily_ic": str(ic_daily_file.resolve()) if ic_daily_file else None,
            "summary": str(ic_summary_file.resolve()) if ic_summary_file else None,
            "status": "preliminary_until_full_validation_period_is_available",
        }
    write_json_atomic(manifest_file, manifest)
    return output_file, manifest_file, ic_daily_file, ic_summary_file


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
        files = discover_files(args.input_dir, args.glob)
        files, pruned_after_end = prune_daily_files_after_end(files, args.end)
        if args.schema_only:
            report = schema_report(files, args.input_dir, args.encoding)
            report["files_pruned_after_end"] = pruned_after_end
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        validate_storage_boundary(args.input_dir, args.output_dir)
        market, input_summary = load_market_data(files, args.input_dir, args)
        input_summary["files_pruned_after_end"] = pruned_after_end
        input_summary["discovery_semantics"] = (
            "启动时固定文件清单；下载程序之后原子发布的新日文件不纳入本次运行。"
        )
        factors = calculate_factors(market, args)
        ic_daily = None
        ic_summary = None
        if args.evaluate:
            ic_daily, ic_summary = evaluate_ic(factors, market, args)
        output_file, manifest_file, ic_daily_file, ic_summary_file = write_outputs(
            factors, input_summary, args, ic_daily, ic_summary
        )
    except (
        FactorPipelineError,
        OSError,
        ValueError,
        KeyError,
        ImportError,
        pd.errors.ParserError,
    ) as exc:
        print(f"处理失败: {exc}", file=sys.stderr)
        return 1

    print(f"处理完成：{len(factors):,} 行，{factors.shape[1] - 2} 个数值列。")
    print(f"因子文件：{output_file.resolve()}")
    print(f"参数与质量报告：{manifest_file.resolve()}")
    if args.evaluate:
        print(f"逐日 IC：{ic_daily_file.resolve()}")
        print(f"IC 汇总：{ic_summary_file.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
