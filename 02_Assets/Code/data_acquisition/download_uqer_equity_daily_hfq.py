import argparse
from pathlib import Path

import pandas as pd

from client import DataAPI


SOURCE_FIELDS = [
    "secID",
    "ticker",
    "secShortName",
    "exchangeCD",
    "tradeDate",
    "preClosePrice",
    "actPreClosePrice",
    "openPrice",
    "highestPrice",
    "lowestPrice",
    "closePrice",
    "turnoverVol",
    "turnoverValue",
    "dealAmount",
    "turnoverRate",
    "accumAdjFactor",
    "negMarketValue",
    "marketValue",
    "isOpen",
    "vwap",
]

COLUMN_RENAME = {
    "secID": "sec_id",
    "ticker": "ticker",
    "secShortName": "sec_short_name",
    "exchangeCD": "exchange_cd",
    "tradeDate": "trade_date",
    "preClosePrice": "pre_close_hfq",
    "actPreClosePrice": "pre_close_raw",
    "openPrice": "open",
    "highestPrice": "high",
    "lowestPrice": "low",
    "closePrice": "close",
    "turnoverVol": "volume_hfq",
    "turnoverValue": "amount",
    "dealAmount": "deal_count",
    "turnoverRate": "turnover_rate",
    "accumAdjFactor": "adj_factor",
    "negMarketValue": "float_market_cap",
    "marketValue": "market_cap",
    "isOpen": "is_open",
    "vwap": "vwap",
}

PROCESSED_COLUMNS = [
    "sec_id",
    "ticker",
    "symbol",
    "sec_short_name",
    "exchange_cd",
    "trade_date",
    "pre_close_hfq",
    "pre_close_raw",
    "open",
    "high",
    "low",
    "close",
    "volume_hfq",
    "amount",
    "deal_count",
    "turnover_rate",
    "adj_factor",
    "float_market_cap",
    "market_cap",
    "is_open",
    "vwap",
]

FLOAT_COLUMNS = [
    "pre_close_hfq",
    "pre_close_raw",
    "open",
    "high",
    "low",
    "close",
    "volume_hfq",
    "amount",
    "turnover_rate",
    "adj_factor",
    "float_market_cap",
    "market_cap",
    "vwap",
]

EXCHANGE_SUFFIX = {
    "XSHG": "SH",
    "XSHE": "SZ",
    "XBEI": "BJ",
    "XBSE": "BJ",
    "BSE": "BJ",
}


class UqerEquityDailyDownloader:
    """下载全A股日频后复权行情，并按交易日保存为 Parquet。"""

    MAX_DATES_PER_REQUEST = 20

    def __init__(
        self,
        start_date: str,
        end_date: str,
        output_root: Path | str | None = None,
    ):
        self.start_date = start_date
        self.end_date = end_date

        if output_root is None:
            output_root = (
                Path.home()
                / "Desktop"
                / "InternData"
                / "StockData"
                / "processed"
                / "uqer_equity_daily_hfq"
            )

        self.output_root = Path(output_root)

    def get_trading_days(self) -> list[str]:
        """获取指定区间内的交易日。"""

        calendar = DataAPI.TradeCalGet(
            exchangeCD="XSHG",
            beginDate=self.start_date,
            endDate=self.end_date,
            field="calendarDate,isOpen",
            pandas="1",
        )

        trading_days = calendar.loc[
            calendar["isOpen"] == 1,
            "calendarDate",
        ]

        return (
            pd.to_datetime(trading_days)
            .dt.strftime("%Y%m%d")
            .tolist()
        )

    def get_output_path(self, trade_date: str) -> Path:
        """生成某个交易日的保存路径。"""

        return (
            self.output_root
            / f"year={trade_date[:4]}"
            / f"month={trade_date[4:6]}"
            / f"{trade_date}.parquet"
        )

    def split_dates(self, trading_days: list[str]) -> list[list[str]]:
        """每20个交易日分为一组。"""

        size = self.MAX_DATES_PER_REQUEST

        return [
            trading_days[start:start + size]
            for start in range(0, len(trading_days), size)
        ]

    def download_batch(self, trading_days: list[str]) -> pd.DataFrame:
        """一次下载不超过20个交易日的全A股后复权行情。"""

        return DataAPI.MktEqudAdjAfGet(
            secID="",
            ticker="",
            tradeDate=trading_days,
            beginDate="",
            endDate="",
            isOpen="",
            field=",".join(SOURCE_FIELDS),
            pandas="1",
        )

    def prepare_daily_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """转换成与正式下载程序相同的字段和数据类型。"""

        data = data.loc[:, SOURCE_FIELDS].rename(columns=COLUMN_RENAME)

        def make_symbol(row):
            suffix = EXCHANGE_SUFFIX.get(str(row["exchange_cd"]))
            if suffix:
                return f"{row['ticker']}.{suffix}"
            return str(row["sec_id"])

        symbol = data.apply(make_symbol, axis=1)
        data.insert(2, "symbol", symbol)

        string_columns = [
            "sec_id",
            "ticker",
            "symbol",
            "sec_short_name",
            "exchange_cd",
        ]
        for column in string_columns:
            data[column] = data[column].astype("string")

        data["trade_date"] = pd.to_datetime(
            data["trade_date"], errors="coerce"
        ).dt.date

        for column in FLOAT_COLUMNS:
            data[column] = pd.to_numeric(data[column], errors="coerce")

        data["deal_count"] = pd.to_numeric(
            data["deal_count"], errors="coerce"
        ).astype("Int64")
        data["is_open"] = pd.to_numeric(
            data["is_open"], errors="coerce"
        ).astype("Int8")

        return (
            data.loc[:, PROCESSED_COLUMNS]
            .sort_values(["symbol", "sec_id"], kind="mergesort")
            .reset_index(drop=True)
        )

    def save_batch(self, data: pd.DataFrame) -> None:
        """把批量结果拆分成每日一个 Parquet 文件。"""

        data = data.copy()
        data["tradeDate"] = pd.to_datetime(data["tradeDate"])

        for trade_date, daily_data in data.groupby("tradeDate"):
            date_string = trade_date.strftime("%Y%m%d")
            output_path = self.get_output_path(date_string)
            daily_data = self.prepare_daily_data(daily_data)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            daily_data.to_parquet(
                output_path,
                index=False,
                engine="pyarrow",
                compression="zstd",
            )

            print(
                f"{date_string}：保存 {len(daily_data)} 行 "
                f"至 {output_path}"
            )

    def run(self) -> None:
        """执行完整下载流程。"""

        trading_days = self.get_trading_days()

        missing_days = [
            day
            for day in trading_days
            if not self.get_output_path(day).exists()
        ]

        batches = self.split_dates(missing_days)

        print(
            f"共 {len(trading_days)} 个交易日，"
            f"待下载 {len(missing_days)} 个，"
            f"需要 {len(batches)} 次行情请求。"
        )

        for number, batch in enumerate(batches, start=1):
            print(
                f"[{number}/{len(batches)}] "
                f"下载 {batch[0]} 至 {batch[-1]}，"
                f"共 {len(batch)} 个交易日"
            )

            data = self.download_batch(batch)
            self.save_batch(data)


def parse_args():
    """读取命令行参数。"""

    parser = argparse.ArgumentParser(
        description="下载指定日期区间的全A股日频后复权行情。"
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
    return parser.parse_args()


def main():
    args = parse_args()

    downloader = UqerEquityDailyDownloader(
        start_date=args.start_date,
        end_date=args.end_date,
        output_root=args.output_root,
    )
    downloader.run()


if __name__ == "__main__":
    main()
