from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "download_uqer_prosperity_indicators.py"
)
SPEC = importlib.util.spec_from_file_location("uqer_prosperity_downloader", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeDataAPI:
    @staticmethod
    def TradeCalGet(**kwargs):
        return pd.DataFrame(
            {
                "calendarDate": ["2024-01-02", "2024-01-03", "2024-01-04"],
                "isOpen": [1, 1, 0],
            }
        )


class ProsperityDownloaderTest(unittest.TestCase):
    def write_workbook(self, root: Path) -> Path:
        path = root / "final.xlsx"
        pd.DataFrame(
            [
                {
                    "行业代码": "801010",
                    "行业名称": "农林牧渔",
                    "UQER指标ID": "2010000007",
                    "UQER中文名": "测试指标",
                    "产业链位置": "上游",
                    "规范统计口径": "年内累计流量",
                    "原统计类型": "累计值",
                    "频率": "月",
                    "单位": "万吨",
                    "UQER API": "getEcoDataIndAgricultural",
                },
                {
                    "行业代码": "801020",
                    "行业名称": "采掘",
                    "UQER指标ID": "2010000007",
                    "UQER中文名": "测试指标",
                    "产业链位置": "中游",
                    "规范统计口径": "年内累计流量",
                    "原统计类型": "累计值",
                    "频率": "月",
                    "单位": "万吨",
                    "UQER API": "getEcoDataIndAgricultural",
                },
            ]
        ).to_excel(path, sheet_name="最终指标表", index=False)
        return path

    def write_catalog(self, root: Path) -> Path:
        path = root / "catalog.csv"
        pd.DataFrame(
            [
                {
                    "metadata_api_name": "getEcoDataIndAgricultural",
                    "api_name": "EcoDataIndAgriculturalGet",
                    "enabled": "1",
                }
            ]
        ).to_csv(path, index=False)
        return path

    def test_build_selection_preserves_industry_mappings_but_deduplicates_requests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mappings = MODULE.load_indicator_mappings(self.write_workbook(root))
            crosswalk = MODULE.load_api_crosswalk(self.write_catalog(root))
            enriched = MODULE.attach_data_apis(mappings, crosswalk)
            requests = MODULE.build_download_requests(enriched)

            self.assertEqual(len(enriched), 2)
            self.assertFalse(enriched.columns.duplicated().any())
            self.assertNotIn("metadata_api_name", enriched.columns)
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests.iloc[0]["uqer_indic_id"], "2010000007")
            self.assertEqual(
                requests.iloc[0]["uqer_api_name"],
                "EcoDataIndAgriculturalGet",
            )

    def test_trade_calendar_keeps_only_open_xshg_days(self):
        calendar = MODULE.download_trade_calendar(
            FakeDataAPI(), "20240101", "20240131"
        )
        self.assertEqual(
            calendar["trade_date"].dt.strftime("%Y-%m-%d").tolist(),
            ["2024-01-02", "2024-01-03"],
        )


if __name__ == "__main__":
    unittest.main()
