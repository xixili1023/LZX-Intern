"""快速读取项目已处理数据，并返回拼接后的 pandas DataFrame。"""

from pathlib import Path
from time import perf_counter

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq


STOCK_DATA_ROOT = (
    Path.home() / "Desktop/InternData/StockData/processed"
)
DYNAMIC_LEADER_ROOT = (
    Path.home()
    / "Desktop/InternData/行业景气度项目Data/processed/dynamic_leaders"
)

DYNAMIC_LEADER_TABLES = {
    "leader_pool": {
        "directory": "leader_pool_daily",
        "date_column": "trade_date",
    },
    "synthetic_nav": {
        "directory": "synthetic_nav_daily",
        "date_column": "trade_date",
    },
    "synthetic_components": {
        "directory": "synthetic_components_daily",
        "date_column": "selection_date",
    },
}

DATASETS = {
    "1": {
        "name": "申万一级行业 VWAP 指数",
        "root": (
            Path.home()
            / "Desktop/InternData/ML期货项目Data/processed/sw_industry_vwap_daily"
        ),
        "date_column": "trade_date",
    },
    "2": {
        "name": "申万及宽基指数日行情",
        "root": STOCK_DATA_ROOT / "uqer_index_daily",
        "date_column": "trade_date",
        "force_float": "amount",
    },
    "3": {
        "name": "全 A 股后复权日行情",
        "root": STOCK_DATA_ROOT / "uqer_equity_daily_hfq",
        "date_column": "trade_date",
    },
    "4": {
        "name": "申万一级行业成分股月度权重",
        "root": STOCK_DATA_ROOT / "uqer_sw_index_weights",
        "date_column": "effective_date",
    },
}


def read_data(data_type, start_date, end_date):
    """按数据类型和日期区间读取 Parquet，返回一个 DataFrame。"""

    choice = str(data_type).strip()
    if choice not in DATASETS:
        raise ValueError("数据类型必须是 1、2、3 或 4")

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")

    config = DATASETS[choice]
    months = pd.period_range(start=start, end=end, freq="M")

    started = perf_counter()
    files = sorted(
        path
        for month in months
        for path in config["root"].glob(
            f"year={month.year}/month={month.month:02d}/*.parquet"
        )
    )
    if not files:
        raise FileNotFoundError(f"未找到 {config['name']} 数据文件")

    schema = pq.read_schema(files[0])
    force_float = config.get("force_float")
    if force_float:
        position = schema.get_field_index(force_float)
        schema = schema.set(
            position,
            pa.field(force_float, pa.float64()),
        )

    date_column = config["date_column"]
    date_type = schema.field(date_column).type
    if pa.types.is_timestamp(date_type):
        start_value = start.to_pydatetime()
        end_value = (end + pd.Timedelta(days=1)).to_pydatetime()
    else:
        start_value = start.date()
        end_value = (end + pd.Timedelta(days=1)).date()

    dataset = ds.dataset(
        [str(path) for path in files],
        format="parquet",
        schema=schema,
    )
    date_filter = (
        ds.field(date_column) >= pa.scalar(start_value, type=date_type)
    ) & (
        ds.field(date_column) < pa.scalar(end_value, type=date_type)
    )
    table = dataset.to_table(filter=date_filter, use_threads=True)
    frame = table.to_pandas(types_mapper=pd.ArrowDtype)

    elapsed = perf_counter() - started
    print(
        f"{config['name']}：{len(files)} 个文件，"
        f"{len(frame):,} 行 × {len(frame.columns)} 列，"
        f"耗时 {elapsed:.4f} 秒"
    )
    return frame


def read_dynamic_leaders(
    table,
    start_date,
    end_date,
    columns=None,
    industry_codes=None,
    asset_types=None,
    root=DYNAMIC_LEADER_ROOT,
):
    """用月份剪枝、Arrow过滤和列投影快速读取动态龙头股数据。"""
    table_name = str(table).strip()
    if table_name not in DYNAMIC_LEADER_TABLES:
        choices = "、".join(DYNAMIC_LEADER_TABLES)
        raise ValueError(f"table 必须是：{choices}")
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")

    config = DYNAMIC_LEADER_TABLES[table_name]
    table_root = Path(root) / config["directory"]
    months = pd.period_range(start=start, end=end, freq="M")
    files = sorted(
        path
        for month in months
        for path in table_root.glob(
            f"year={month.year}/month={month.month:02d}/*.parquet"
        )
    )
    if not files:
        raise FileNotFoundError(f"未找到动态龙头股数据文件: {table_root}")

    schema = pq.read_schema(files[0])
    requested_columns = None if columns is None else list(columns)
    if requested_columns is not None:
        missing = set(requested_columns) - set(schema.names)
        if missing:
            raise ValueError(f"请求的字段不存在: {sorted(missing)}")

    date_column = config["date_column"]
    date_type = schema.field(date_column).type
    date_filter = (
        ds.field(date_column) >= pa.scalar(start.to_pydatetime(), type=date_type)
    ) & (
        ds.field(date_column)
        < pa.scalar((end + pd.Timedelta(days=1)).to_pydatetime(), type=date_type)
    )
    filters = date_filter
    if industry_codes:
        filters = filters & ds.field("industry_code").isin(
            [str(code) for code in industry_codes]
        )
    if asset_types:
        if table_name != "leader_pool":
            raise ValueError("asset_types 仅适用于 leader_pool")
        filters = filters & ds.field("asset_type").isin(
            [str(value).upper() for value in asset_types]
        )

    dataset = ds.dataset([str(path) for path in files], format="parquet", schema=schema)
    arrow_table = dataset.to_table(
        columns=requested_columns,
        filter=filters,
        use_threads=True,
    )
    return arrow_table.to_pandas(types_mapper=pd.ArrowDtype)


def main():
    print("请选择数据类型：")
    for number, config in DATASETS.items():
        print(f"{number}. {config['name']}")

    data_type = input("输入编号：").strip()
    start_date = input("输入开始日期（YYYY-MM-DD）：").strip()
    end_date = input("输入结束日期（YYYY-MM-DD）：").strip()

    return read_data(data_type, start_date, end_date)


if __name__ == "__main__":
    df = main()
    print(df.head())
