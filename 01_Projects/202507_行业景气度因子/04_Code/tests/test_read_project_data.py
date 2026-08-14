from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


MODULE_PATH = Path(__file__).parents[1] / "data" / "read_project_data.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("统一数据读取器尚未实现")
    spec = importlib.util.spec_from_file_location("read_project_data", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ReadProjectDataTest(unittest.TestCase):
    def test_read_dynamic_leaders_prunes_months_and_filters_before_pandas(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for month, rows in {
                "01": [
                    ("2026-01-30", "801010", "REAL", "000001"),
                    ("2026-01-30", "801020", "SYNTH", "SYNTH_2"),
                ],
                "02": [
                    ("2026-02-02", "801010", "SYNTH", "SYNTH_1"),
                    ("2026-02-03", "801010", "REAL", "000002"),
                ],
                "03": [("2026-03-02", "801010", "REAL", "000003")],
            }.items():
                month_dir = root / "leader_pool_daily" / "year=2026" / f"month={month}"
                month_dir.mkdir(parents=True)
                pd.DataFrame(
                    rows,
                    columns=["trade_date", "industry_code", "asset_type", "asset_id"],
                ).assign(trade_date=lambda x: pd.to_datetime(x.trade_date)).to_parquet(
                    month_dir / f"2026{month}.parquet", index=False
                )

            result = module.read_dynamic_leaders(
                "leader_pool",
                "2026-01-31",
                "2026-02-02",
                columns=["trade_date", "asset_id"],
                industry_codes=["801010"],
                asset_types=["SYNTH"],
                root=root,
            )

        self.assertEqual(result.columns.tolist(), ["trade_date", "asset_id"])
        self.assertEqual(result["asset_id"].tolist(), ["SYNTH_1"])

    def test_read_dynamic_components_uses_selection_date(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            month = root / "synthetic_components_daily/year=2026/month=02"
            month.mkdir(parents=True)
            pd.DataFrame(
                {
                    "selection_date": pd.to_datetime(["2026-02-02"]),
                    "industry_code": ["801010"],
                    "component_ticker": ["000001"],
                }
            ).to_parquet(month / "202602.parquet", index=False)

            result = module.read_dynamic_leaders(
                "synthetic_components", "2026-02-02", "2026-02-02", root=root
            )

        self.assertEqual(result["component_ticker"].tolist(), ["000001"])

    def test_read_data_concatenates_files_and_keeps_requested_dates(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            month = root / "year=2022" / "month=12"
            month.mkdir(parents=True)
            pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2022-12-01"]),
                    "industry_vwap": [101.0],
                }
            ).to_parquet(month / "part-1.parquet", index=False)
            pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(
                        ["2022-12-30", "2023-01-02"]
                    ),
                    "industry_vwap": [102.0, 103.0],
                }
            ).to_parquet(month / "part-2.parquet", index=False)

            datasets = {
                "1": {
                    "name": "申万一级行业 VWAP 指数",
                    "root": root,
                    "date_column": "trade_date",
                }
            }
            with patch.object(module, "DATASETS", datasets):
                result = module.read_data(
                    "1", "2022-12-01", "2022-12-31"
                )

        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(result["industry_vwap"].tolist(), [101.0, 102.0])
        self.assertEqual(
            pd.to_datetime(result["trade_date"]).dt.strftime("%Y-%m-%d").tolist(),
            ["2022-12-01", "2022-12-30"],
        )

    def test_read_data_unifies_mixed_index_amount_types(self):
        module = load_module()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            month = root / "year=2022" / "month=12"
            month.mkdir(parents=True)
            pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2022-12-01"]),
                    "ticker": ["801010"],
                    "amount": pd.Series([100], dtype="int64"),
                }
            ).to_parquet(month / "part-1.parquet", index=False)
            pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2022-12-02"]),
                    "ticker": ["801010"],
                    "amount": [100.5],
                }
            ).to_parquet(month / "part-2.parquet", index=False)

            datasets = {
                "2": {
                    "name": "申万及宽基指数日行情",
                    "root": root,
                    "date_column": "trade_date",
                    "force_float": "amount",
                }
            }
            with patch.object(module, "DATASETS", datasets):
                result = module.read_data(
                    "2", "2022-12-01", "2022-12-31"
                )

        self.assertEqual(result["amount"].tolist(), [100.0, 100.5])


if __name__ == "__main__":
    unittest.main()
