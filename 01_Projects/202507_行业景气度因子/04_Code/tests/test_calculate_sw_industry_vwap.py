import importlib.util
import tempfile
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).parents[1] / "data" / "calculate_sw_industry_vwap.py"
SPEC = importlib.util.spec_from_file_location("calculate_sw_industry_vwap", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CalculateIndustryVwapTest(unittest.TestCase):
    def test_save_monthly_files_uses_fixed_names_without_cleaning_output(self):
        result = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2018-01-02", "2018-02-01"]),
                "index_ticker": ["801010", "801010"],
                "index_short_name_source": ["农林牧渔", "农林牧渔"],
                "industry_vwap_return": [pd.NA, 0.01],
                "industry_vwap": [100.0, 101.0],
            }
        )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sw_industry_vwap_daily"
            output.mkdir()
            (output / "old-uuid.parquet").touch()

            MODULE.save_monthly_files(result, output)

            self.assertEqual(
                sorted(path.relative_to(output).as_posix() for path in output.rglob("*.parquet")),
                [
                    "old-uuid.parquet",
                    "year=2018/month=01/201801.parquet",
                    "year=2018/month=02/201802.parquet",
                ],
            )

    def test_list_parquet_files_ignores_manifest_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parquet = root / "year=2017" / "month=12" / "20171229.parquet"
            manifest = root / "manifests" / "run.json"
            parquet.parent.mkdir(parents=True)
            manifest.parent.mkdir(parents=True)
            parquet.touch()
            manifest.touch()

            self.assertEqual(MODULE.list_parquet_files(root), [parquet])

    def test_uses_monthly_weights_and_starts_at_100(self):
        stocks = pd.DataFrame(
            {
                "ticker": [
                    "000001",
                    "000001",
                    "000001",
                    "000002",
                    "000002",
                    "000002",
                ],
                "trade_date": pd.to_datetime(
                    ["2017-12-29", "2018-01-02", "2018-01-03"] * 2
                ),
                "vwap": [100.0, 110.0, 121.0, 200.0, 180.0, 198.0],
            }
        )
        weights = pd.DataFrame(
            {
                "index_ticker": ["801010", "801010"],
                "index_short_name_source": ["农林牧渔", "农林牧渔"],
                "constituent_ticker": ["000001", "000002"],
                "effective_date": pd.to_datetime(["2017-12-29", "2017-12-29"]),
                "weight": [25.0, 75.0],
            }
        )

        result = MODULE.calculate_industry_vwap(stocks, weights, start_date="2018-01-01")

        self.assertEqual(
            result["trade_date"].tolist(),
            list(pd.to_datetime(["2018-01-02", "2018-01-03"])),
        )
        self.assertTrue(pd.isna(result.loc[0, "industry_vwap_return"]))
        self.assertAlmostEqual(result.loc[0, "industry_vwap"], 100.0)
        self.assertAlmostEqual(result.loc[1, "industry_vwap_return"], 0.10)
        self.assertAlmostEqual(result.loc[1, "industry_vwap"], 110.0)


if __name__ == "__main__":
    unittest.main()
