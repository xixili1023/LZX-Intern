from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "process_uqer_prosperity_indicators.py"
)
SPEC = importlib.util.spec_from_file_location("uqer_prosperity_processor", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ProsperityProcessorTest(unittest.TestCase):
    def test_cumulative_flow_is_deaccumulated_with_annual_reset(self):
        dates = pd.to_datetime(
            [f"2023-{month:02d}-28" for month in range(1, 13)]
            + [f"2024-{month:02d}-28" for month in range(1, 13)]
        )
        cumulative = list(np.cumsum(np.repeat(10.0, 12))) + list(
            np.cumsum(np.repeat(12.0, 12))
        )
        result = MODULE.transform_values(
            pd.Series(cumulative),
            pd.Series(dates),
            normalized_stat_type="年内累计流量",
            frequency="月",
            unit="万吨",
        )
        self.assertTrue(np.isnan(result["transformed_value"].iloc[11]))
        self.assertAlmostEqual(
            result["period_value"].iloc[12], 12.0, places=8
        )
        self.assertAlmostEqual(
            result["transformed_value"].iloc[12], np.log(1.2), places=8
        )

    def test_missing_publish_date_is_excluded_and_updates_keep_latest(self):
        raw = pd.DataFrame(
            [
                {
                    "indicID": "1",
                    "periodDate": "20240131",
                    "publishDate": None,
                    "dataValue": 1,
                    "updateTime": "20240201T000000",
                },
                {
                    "indicID": "1",
                    "periodDate": "20240131",
                    "publishDate": "20240202",
                    "dataValue": 2,
                    "updateTime": "20240202T000000",
                },
                {
                    "indicID": "1",
                    "periodDate": "20240131",
                    "publishDate": "20240202",
                    "dataValue": 3,
                    "updateTime": "20240203T000000",
                },
            ]
        )
        clean, audit = MODULE.prepare_observations(raw)
        self.assertEqual(len(clean), 1)
        self.assertEqual(clean.iloc[0]["raw_value"], 3)
        self.assertEqual(audit["missing_publish_date_excluded"], 1)
        self.assertEqual(audit["superseded_updates_removed"], 1)

    def test_availability_and_chain_lag_use_future_open_days(self):
        calendar = pd.DataFrame(
            {"trade_date": pd.bdate_range("2024-02-01", periods=30)}
        )
        publish = pd.Series(pd.to_datetime(["2024-02-02"]))  # Friday
        available, effective = MODULE.map_effective_dates(
            publish, calendar, chain_position="下游", lag_days=5
        )
        self.assertEqual(available.iloc[0], pd.Timestamp("2024-02-05"))
        self.assertEqual(effective.iloc[0], pd.Timestamp("2024-02-12"))

    def test_robust_zscore_uses_only_prior_observations(self):
        values = pd.Series([1.0, 2.0, 3.0, 4.0, 100.0])
        first = MODULE.rolling_robust_zscore(values, window=3, min_periods=3)
        changed = MODULE.rolling_robust_zscore(
            pd.Series([1.0, 2.0, 3.0, 4.0, -1000.0]),
            window=3,
            min_periods=3,
        )
        self.assertTrue(first.iloc[:3].isna().all())
        self.assertAlmostEqual(first.iloc[3], changed.iloc[3], places=12)
        self.assertAlmostEqual(first.iloc[3], 2.0 / 1.4826, places=8)

    def test_process_snapshot_writes_event_and_partitioned_daily_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_snapshot = root / "raw" / "snapshot=test"
            data_dir = raw_snapshot / "data" / "api=FakeGet"
            data_dir.mkdir(parents=True)
            periods = pd.date_range("2020-01-31", periods=48, freq="ME")
            raw = pd.DataFrame(
                {
                    "indicID": "1",
                    "periodDate": periods.strftime("%Y%m%d"),
                    "publishDate": (periods + pd.Timedelta(days=10)).strftime(
                        "%Y%m%d"
                    ),
                    "dataValue": np.arange(1.0, 49.0),
                    "updateTime": (periods + pd.Timedelta(days=11)).strftime(
                        "%Y-%m-%dT00:00:00"
                    ),
                }
            )
            raw.to_parquet(data_dir / "part-0001.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "行业代码": "801010",
                        "行业名称": "测试行业",
                        "UQER指标ID": "1",
                        "UQER中文名": "测试指标",
                        "产业链位置": "下游",
                        "规范统计口径": "当期流量/数量",
                        "原统计类型": "当期值",
                        "频率": "月",
                        "单位": "万吨",
                    }
                ]
            ).to_parquet(raw_snapshot / "indicator_selection.parquet", index=False)
            pd.DataFrame(
                {"trade_date": pd.bdate_range("2020-01-01", "2024-03-31")}
            ).to_parquet(raw_snapshot / "xshg_trade_calendar.parquet", index=False)
            (raw_snapshot / "manifest.json").write_text(
                json.dumps(
                    {"date_range": {"start": "20200101", "end": "20240331"}}
                ),
                encoding="utf-8",
            )

            target = MODULE.process_snapshot(
                raw_snapshot,
                root / "processed",
                "test",
                {"上游": 20, "中游": 10, "下游": 5},
            )
            events = pd.read_parquet(target / "factor_events.parquet")
            daily_files = list((target / "factor_daily").rglob("*.parquet"))
            daily = pd.concat([pd.read_parquet(path) for path in daily_files])
            report = json.loads((target / "quality_report.json").read_text())

            self.assertEqual(len(events), 48)
            self.assertGreater(events["factor_value"].notna().sum(), 0)
            self.assertGreater(len(daily), 0)
            self.assertEqual(report["observation_audit"]["output_rows"], 48)


if __name__ == "__main__":
    unittest.main()
