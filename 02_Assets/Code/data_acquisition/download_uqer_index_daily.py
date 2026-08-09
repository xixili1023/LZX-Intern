import argparse
from pathlib import Path

import pandas as pd

from client import DataAPI


SW2021_START_DATE = "20211213"

SW2014_INDEXES = {
    "801010": "农林牧渔", "801020": "采掘", "801030": "化工",
    "801040": "钢铁", "801050": "有色金属", "801080": "电子",
    "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服装",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业",
    "801170": "交通运输", "801180": "房地产", "801200": "商业贸易",
    "801210": "休闲服务", "801230": "综合", "801710": "建筑材料",
    "801720": "建筑装饰", "801730": "电气设备", "801740": "国防军工",
    "801750": "计算机", "801760": "传媒", "801770": "通信",
    "801780": "银行", "801790": "非银金融", "801880": "汽车",
    "801890": "机械设备",
}

SW2021_INDEXES = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁",
    "801050": "有色金属", "801080": "电子", "801110": "家用电器",
    "801120": "食品饮料", "801130": "纺织服饰", "801140": "轻工制造",
    "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务",
    "801230": "综合", "801710": "建筑材料", "801720": "建筑装饰",
    "801730": "电力设备", "801740": "国防军工", "801750": "计算机",
    "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备",
    "801950": "煤炭", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理",
}

BROAD_INDEXES = {
    "000300": "沪深300",
    "000905": "中证500",
    "000852": "中证1000",
}

SOURCE_FIELDS = [
    "indexID", "ticker", "secShortName", "exchangeCD", "tradeDate",
    "preCloseIndex", "openIndex", "lowestIndex", "highestIndex",
    "closeIndex", "turnoverVol", "turnoverValue", "CHG", "CHGPct",
]

COLUMN_RENAME = {
    "indexID": "index_id",
    "ticker": "ticker",
    "secShortName": "sec_short_name",
    "exchangeCD": "exchange_cd",
    "tradeDate": "trade_date",
    "preCloseIndex": "pre_close",
    "openIndex": "open",
    "lowestIndex": "low",
    "highestIndex": "high",
    "closeIndex": "close",
    "turnoverVol": "volume",
    "turnoverValue": "amount",
    "CHG": "change",
    "CHGPct": "change_pct",
}

PROCESSED_COLUMNS = [
    "index_id", "ticker", "sec_short_name", "exchange_cd", "trade_date",
    "index_family", "classification_version", "classification_name",
    "pre_close", "open", "low", "high", "close", "volume", "amount",
    "change", "change_pct",
]

FLOAT_COLUMNS = [
    "pre_close", "open", "low", "high", "close", "volume", "amount",
    "change", "change_pct",
]


class UqerIndexDailyDownloader:
    """下载申万一级行业指数和宽基指数日行情。"""

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
                / "uqer_index_daily"
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

        return pd.to_datetime(trading_days).dt.strftime("%Y%m%d").tolist()

    def get_output_path(self, trade_date: str) -> Path:
        """生成某个交易日的保存路径。"""

        return (
            self.output_root
            / f"year={trade_date[:4]}"
            / f"month={trade_date[4:6]}"
            / f"{trade_date}.parquet"
        )

    def get_version(self, trade_date: str) -> str:
        """返回交易日对应的申万行业分类版本。"""

        return "SW2021" if trade_date >= SW2021_START_DATE else "SW2014"

    def get_tickers(self, version: str) -> list[str]:
        """返回指定版本的行业指数和宽基指数代码。"""

        industry_indexes = (
            SW2021_INDEXES if version == "SW2021" else SW2014_INDEXES
        )
        return list(industry_indexes) + list(BROAD_INDEXES)

    def build_batches(
        self,
        trading_days: list[str],
        missing_days: list[str],
    ) -> list[tuple[str, list[str]]]:
        """把连续缺失日期按版本分组，再按每20个交易日切分。"""

        missing_set = set(missing_days)
        consecutive_groups = []
        current_group = []

        for day in trading_days:
            if day in missing_set:
                current_group.append(day)
            elif current_group:
                consecutive_groups.append(current_group)
                current_group = []

        if current_group:
            consecutive_groups.append(current_group)

        batches = []
        for group in consecutive_groups:
            for version in ("SW2014", "SW2021"):
                version_days = [
                    day for day in group if self.get_version(day) == version
                ]
                for start in range(0, len(version_days), self.MAX_DATES_PER_REQUEST):
                    batch = version_days[start:start + self.MAX_DATES_PER_REQUEST]
                    if batch:
                        batches.append((version, batch))
        return batches

    def download_batch(
        self,
        trading_days: list[str],
        version: str,
    ) -> pd.DataFrame:
        """下载一批行业指数和宽基指数行情。"""

        return DataAPI.MktIdxdGet(
            indexID="",
            ticker=",".join(self.get_tickers(version)),
            tradeDate="",
            beginDate=trading_days[0],
            endDate=trading_days[-1],
            exchangeCD="",
            field=",".join(SOURCE_FIELDS),
            pandas="1",
        )

    def prepare_daily_data(
        self,
        data: pd.DataFrame,
        version: str,
    ) -> pd.DataFrame:
        """转换成与正式指数下载程序相同的字段和数据类型。"""

        data = data.loc[:, SOURCE_FIELDS].rename(columns=COLUMN_RENAME)
        industry_indexes = (
            SW2021_INDEXES if version == "SW2021" else SW2014_INDEXES
        )

        def classify(ticker):
            ticker = str(ticker)
            if ticker in BROAD_INDEXES:
                return "broad_market", "not_applicable", BROAD_INDEXES[ticker]
            return "sw_level1", version, industry_indexes[ticker]

        classification = data["ticker"].apply(classify)
        data["index_family"] = classification.map(lambda value: value[0])
        data["classification_version"] = classification.map(
            lambda value: value[1]
        )
        data["classification_name"] = classification.map(lambda value: value[2])

        string_columns = [
            "index_id",
            "ticker",
            "sec_short_name",
            "exchange_cd",
            "index_family",
            "classification_version",
            "classification_name",
        ]
        for column in string_columns:
            data[column] = data[column].astype("string")

        data["trade_date"] = pd.to_datetime(
            data["trade_date"], errors="coerce"
        ).dt.date

        for column in FLOAT_COLUMNS:
            data[column] = pd.to_numeric(data[column], errors="coerce")

        return (
            data.loc[:, PROCESSED_COLUMNS]
            .sort_values(["index_family", "ticker"], kind="mergesort")
            .reset_index(drop=True)
        )

    def save_batch(self, data: pd.DataFrame, version: str) -> None:
        """把批量结果拆分成每日一个 Parquet 文件。"""

        data = data.copy()
        data["tradeDate"] = pd.to_datetime(data["tradeDate"])

        for trade_date, daily_data in data.groupby("tradeDate"):
            date_string = trade_date.strftime("%Y%m%d")
            output_path = self.get_output_path(date_string)
            daily_data = self.prepare_daily_data(daily_data, version)

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
        batches = self.build_batches(trading_days, missing_days)

        print(
            f"共 {len(trading_days)} 个交易日，"
            f"待下载 {len(missing_days)} 个，"
            f"需要 {len(batches)} 次行情请求。"
        )

        for number, (version, batch) in enumerate(batches, start=1):
            print(
                f"[{number}/{len(batches)}] "
                f"下载 {batch[0]} 至 {batch[-1]}，"
                f"共 {len(batch)} 个交易日，{version}"
            )

            data = self.download_batch(batch, version)
            self.save_batch(data, version)


def parse_args():
    """读取命令行参数。"""

    parser = argparse.ArgumentParser(
        description="下载申万一级行业指数和宽基指数日行情。"
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

    downloader = UqerIndexDailyDownloader(
        start_date=args.start_date,
        end_date=args.end_date,
        output_root=args.output_root,
    )
    downloader.run()


if __name__ == "__main__":
    main()