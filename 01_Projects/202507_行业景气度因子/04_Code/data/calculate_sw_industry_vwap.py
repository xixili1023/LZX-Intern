"""用申万月度权重和个股后复权 VWAP 收益合成日频行业 VWAP 指数。

运行：python calculate_sw_industry_vwap.py
基准：2018 年各行业第一条交易日记录设为 100。
输出：单独保存，并按 year/month 分区。
"""

from argparse import ArgumentParser
from pathlib import Path

import pandas as pd


DEFAULT_STOCK_PATH = Path.home() / "Desktop/InternData/StockData/processed/uqer_equity_daily_hfq"
DEFAULT_WEIGHT_PATH = Path.home() / "Desktop/InternData/StockData/processed/uqer_sw_index_weights"
DEFAULT_OUTPUT_PATH = (
    Path.home()
    / "Desktop/InternData/ML期货项目Data/processed/sw_industry_vwap_daily"
)


def list_parquet_files(path):
    path = Path(path)
    return [path] if path.is_file() else sorted(path.rglob("*.parquet"))


def save_monthly_files(result, output_path):
    output_path = Path(output_path)
    data = result.copy()
    data["year"] = data["trade_date"].dt.year
    data["month"] = data["trade_date"].dt.month
    for (year, month), monthly_data in data.groupby(["year", "month"]):
        month_dir = output_path / f"year={year}" / f"month={month:02d}"
        month_dir.mkdir(parents=True, exist_ok=True)
        monthly_data.drop(columns=["year", "month"]).to_parquet(
            month_dir / f"{year}{month:02d}.parquet",
            index=False,
        )


def calculate_industry_vwap(stocks, weights, start_date="2018-01-01"):
    stocks = stocks[["ticker", "trade_date", "vwap"]].copy()
    weights = weights[
        [
            "index_ticker",
            "index_short_name_source",
            "constituent_ticker",
            "effective_date",
            "weight",
        ]
    ].copy()

    stocks["ticker"] = stocks["ticker"].astype(str).str.zfill(6)
    weights["constituent_ticker"] = weights["constituent_ticker"].astype(str).str.zfill(6)
    stocks["trade_date"] = pd.to_datetime(stocks["trade_date"])
    weights["effective_date"] = pd.to_datetime(weights["effective_date"])

    stocks = stocks.sort_values(["ticker", "trade_date"])
    stocks["vwap_return"] = stocks.groupby("ticker")["vwap"].pct_change(fill_method=None)
    stocks = stocks.loc[stocks["trade_date"] >= pd.Timestamp(start_date)]

    calendar = pd.DataFrame({"trade_date": stocks["trade_date"].drop_duplicates().sort_values()})
    effective_dates = weights[["effective_date"]].drop_duplicates().sort_values("effective_date")
    calendar = pd.merge_asof(
        calendar,
        effective_dates,
        left_on="trade_date",
        right_on="effective_date",
        direction="backward",
        allow_exact_matches=False,
    ).dropna()

    panel = calendar.merge(weights, on="effective_date", how="inner")
    panel = panel.merge(
        stocks[["ticker", "trade_date", "vwap_return"]],
        left_on=["constituent_ticker", "trade_date"],
        right_on=["ticker", "trade_date"],
        how="left",
    ).dropna(subset=["vwap_return", "weight"])
    panel["weighted_return"] = panel["weight"] * panel["vwap_return"]

    keys = ["index_ticker", "index_short_name_source", "trade_date"]
    result = panel.groupby(keys, as_index=False).agg(
        weighted_return=("weighted_return", "sum"),
        available_weight=("weight", "sum"),
    )
    result["industry_vwap_return"] = result["weighted_return"] / result["available_weight"]
    result = result.sort_values(["index_ticker", "trade_date"]).reset_index(drop=True)

    first_rows = ~result.duplicated("index_ticker")
    growth = 1.0 + result["industry_vwap_return"]
    growth.loc[first_rows] = 1.0
    result["industry_vwap"] = 100.0 * growth.groupby(result["index_ticker"]).cumprod()
    result.loc[first_rows, "industry_vwap_return"] = pd.NA

    return result[
        [
            "trade_date",
            "index_ticker",
            "index_short_name_source",
            "industry_vwap_return",
            "industry_vwap",
        ]
    ]


def main():
    parser = ArgumentParser(description="合成申万一级行业 VWAP 指数")
    parser.add_argument("--stock-path", type=Path, default=DEFAULT_STOCK_PATH)
    parser.add_argument("--weight-path", type=Path, default=DEFAULT_WEIGHT_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--start-date", default="2018-01-01")
    args = parser.parse_args()

    stocks = pd.read_parquet(
        list_parquet_files(args.stock_path),
        columns=["ticker", "trade_date", "vwap"],
    )
    weights = pd.read_parquet(
        list_parquet_files(args.weight_path),
        columns=[
            "index_ticker",
            "index_short_name_source",
            "constituent_ticker",
            "effective_date",
            "weight",
        ],
    )
    result = calculate_industry_vwap(stocks, weights, args.start_date)
    save_monthly_files(result, args.output_path)
    print(f"已保存 {len(result):,} 行：{args.output_path}")


if __name__ == "__main__":
    main()
