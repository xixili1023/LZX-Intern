import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


MODULE_PATH = Path(__file__).parents[1] / "data" / "build_dynamic_leaders.py"
SPEC = importlib.util.spec_from_file_location("build_dynamic_leaders", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DynamicLeaderSelectionTest(unittest.TestCase):
    def test_daily_weights_use_latest_known_snapshot_without_backfill(self):
        weights = pd.DataFrame(
            {
                "index_ticker": ["801010", "801010", "801010"],
                "effective_date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-02-01"]),
                "constituent_ticker": ["000001", "000002", "000001"],
                "weight": [0.6, 0.4, 1.0],
            }
        )
        dates = pd.to_datetime(["2025-12-31", "2026-01-15", "2026-02-02"])

        result = MODULE.expand_weight_snapshots(weights, dates)

        self.assertEqual(result["trade_date"].drop_duplicates().tolist(), list(dates[1:]))
        jan = result.loc[result["trade_date"] == dates[1]].set_index("constituent_ticker")
        feb = result.loc[result["trade_date"] == dates[2]].set_index("constituent_ticker")
        self.assertAlmostEqual(jan.loc["000002", "weight"], 0.4)
        self.assertNotIn("000002", feb.index)

    def test_eligibility_uses_90_day_denominator_and_zero_for_absent_weights(self):
        dates = pd.bdate_range("2026-01-01", periods=90)
        stocks = pd.DataFrame(
            {
                "trade_date": dates,
                "ticker": "000001",
                "close": 101.0,
                "pre_close_hfq": 100.0,
                "is_open": [0] * 9 + [1] * 81,
            }
        )
        daily_weights = pd.concat(
            [
                pd.DataFrame(
                    {
                        "trade_date": dates,
                        "index_ticker": "801010",
                        "constituent_ticker": "000002",
                        "weight": [1.0] * 45 + [0.8] * 45,
                    }
                ),
                pd.DataFrame(
                    {
                        "trade_date": dates[-45:],
                        "index_ticker": "801010",
                        "constituent_ticker": "000001",
                        "weight": 0.20,
                    }
                ),
            ],
            ignore_index=True,
        )

        result = MODULE.build_qualified_pool(
            stocks, daily_weights, "801010", dates[-1], dates
        )

        self.assertEqual(result["ticker"].tolist(), ["000001"])
        self.assertAlmostEqual(result.iloc[0]["obs_ratio"], 0.9)
        self.assertAlmostEqual(result.iloc[0]["avg_weight_90"], 0.10)

    def test_normalize_weight_units_converts_percent_points(self):
        weights = pd.DataFrame(
            {
                "index_ticker": ["801010", "801010"],
                "effective_date": pd.to_datetime(["2026-01-30"] * 2),
                "constituent_ticker": ["000001", "000002"],
                "weight": [60.0, 40.0],
            }
        )

        result = MODULE.normalize_weight_units(weights)

        self.assertEqual(result["weight"].tolist(), [0.6, 0.4])

    def test_zero_high_weight_names_creates_one_equal_weight_top3_synth(self):
        qualified = pd.DataFrame(
            {
                "ticker": ["000001", "000002", "000003", "000004"],
                "avg_weight_90": [0.09, 0.08, 0.07, 0.06],
                "obs_ratio": [1.0, 0.99, 0.98, 1.0],
                "te": [0.1, 0.2, 0.3, 0.4],
                "rho": [0.8, 0.7, 0.6, 0.5],
            }
        )

        leaders, components = MODULE.select_leaders_for_industry(
            qualified, "801010", "2026-08-10"
        )

        self.assertEqual(leaders["asset_id"].tolist(), ["SYNTH_SW_801010_20260810"])
        self.assertEqual(leaders["asset_type"].tolist(), ["SYNTH"])
        self.assertTrue(leaders["score"].isna().all())
        self.assertEqual(components["component_ticker"].tolist(), ["000001", "000002", "000003"])
        np.testing.assert_allclose(components["target_weight"], [1 / 3, 1 / 3, 1 / 3])

    def test_one_to_three_high_weight_names_are_kept_without_scoring(self):
        qualified = pd.DataFrame(
            {
                "ticker": ["000001", "000002", "000003", "000004"],
                "avg_weight_90": [0.15, 0.12, 0.10, 0.09],
                "obs_ratio": [1.0] * 4,
                "te": [np.nan] * 4,
                "rho": [np.nan] * 4,
            }
        )

        leaders, components = MODULE.select_leaders_for_industry(
            qualified, "801010", "2026-08-10"
        )

        self.assertEqual(leaders["stock_ticker"].tolist(), ["000001", "000002", "000003"])
        self.assertTrue(leaders["score"].isna().all())
        self.assertTrue(components.empty)

    def test_more_than_three_high_weight_names_use_complete_score_and_tiebreaks(self):
        qualified = pd.DataFrame(
            {
                "ticker": ["000001", "000002", "000003", "000004", "000005"],
                "avg_weight_90": [0.20, 0.18, 0.15, 0.12, 0.05],
                "obs_ratio": [1.0] * 5,
                "te": [0.10, 0.20, 0.40, 0.20, 0.50],
                "rho": [0.0, 1.0, 1.0, 1.0, 0.0],
            }
        )

        leaders, _ = MODULE.select_leaders_for_industry(
            qualified, "801010", "2026-08-10"
        )

        # TE95 is computed from all five qualified names: 0.48.
        # 000002 and 000004 tie on score, so higher avg_weight_90 wins.
        self.assertEqual(leaders["stock_ticker"].tolist(), ["000002", "000004", "000001"])
        expected_third = 0.60 * (1 - 0.10 / 0.48) + 0.40 * 0.5
        self.assertAlmostEqual(leaders.iloc[2]["score"], expected_third)


class SyntheticSeriesTest(unittest.TestCase):
    def test_incremental_nav_starts_from_saved_nav_and_previous_components(self):
        returns = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-08-11"] * 3),
                "ticker": ["A", "B", "C"],
                "stock_return": [0.03, 0.06, -0.03],
            }
        )
        selections = pd.DataFrame(
            {
                "selection_date": pd.to_datetime(["2026-08-10"] * 3),
                "industry_code": ["801010"] * 3,
                "component_ticker": ["A", "B", "C"],
                "target_weight": [1 / 3] * 3,
            }
        )

        result = MODULE.compute_synthetic_nav(
            returns,
            selections,
            initial_nav={"801010": 250.0},
            start_date="2026-08-11",
        )

        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result.iloc[0]["synth_return_gross"], 0.02)
        self.assertAlmostEqual(result.iloc[0]["synth_close_gross"], 255.0)

    def test_return_uses_previous_dates_components_and_nav_stays_continuous(self):
        returns = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-08-10"] * 4 + ["2026-08-11"] * 4),
                "ticker": ["A", "B", "C", "D"] * 2,
                "stock_return": [0.0, 0.0, 0.0, 0.0, 0.03, 0.06, -0.03, 0.30],
            }
        )
        selections = pd.DataFrame(
            {
                "selection_date": pd.to_datetime(["2026-08-09"] * 3 + ["2026-08-10"] * 3),
                "industry_code": ["801010"] * 6,
                "component_ticker": ["A", "B", "C", "A", "B", "D"],
                "target_weight": [1 / 3] * 6,
            }
        )

        result = MODULE.compute_synthetic_nav(
            returns, selections, initial_nav=100.0
        )

        day_10 = result.loc[result["trade_date"] == pd.Timestamp("2026-08-10")].iloc[0]
        day_11 = result.loc[result["trade_date"] == pd.Timestamp("2026-08-11")].iloc[0]
        self.assertAlmostEqual(day_10["synth_return_gross"], 0.0)
        self.assertAlmostEqual(day_10["internal_turnover"], 1 / 3)
        self.assertAlmostEqual(day_11["synth_return_gross"], 0.13)
        self.assertAlmostEqual(day_11["synth_close_gross"], 113.0)


class MonthlyStorageTest(unittest.TestCase):
    def test_incremental_range_reads_only_91_days_and_skips_when_current(self):
        dates = pd.bdate_range("2026-01-01", periods=100)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stock_root = root / "stocks"
            output_root = root / "output"
            for date in dates:
                path = stock_root / f"year={date.year}/month={date.month:02d}/{date:%Y%m%d}.parquet"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            leader_month = output_root / f"leader_pool_daily/year={dates[94].year}/month={dates[94].month:02d}"
            leader_month.mkdir(parents=True)
            pd.DataFrame({"trade_date": [dates[94]]}).to_parquet(
                leader_month / f"{dates[94]:%Y%m}.parquet", index=False
            )

            update_range = MODULE.resolve_incremental_range(stock_root, output_root)
            current_month = output_root / f"leader_pool_daily/year={dates[99].year}/month={dates[99].month:02d}"
            current_month.mkdir(parents=True, exist_ok=True)
            pd.DataFrame({"trade_date": [dates[99]]}).to_parquet(
                current_month / f"{dates[99]:%Y%m}.parquet", index=False
            )
            no_update = MODULE.resolve_incremental_range(stock_root, output_root)

        self.assertEqual(update_range["input_start"], dates[5])
        self.assertEqual(update_range["output_start"], dates[95])
        self.assertEqual(update_range["end"], dates[99])
        self.assertIsNone(no_update)

    def test_incremental_state_reads_last_nav_and_components(self):
        date = pd.Timestamp("2026-08-10")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nav_dir = root / "synthetic_nav_daily/year=2026/month=08"
            component_dir = root / "synthetic_components_daily/year=2026/month=08"
            nav_dir.mkdir(parents=True)
            component_dir.mkdir(parents=True)
            pd.DataFrame(
                {
                    "trade_date": [date, date],
                    "industry_code": ["801010", "801020"],
                    "synth_close_gross": [123.0, 456.0],
                }
            ).to_parquet(nav_dir / "202608.parquet", index=False)
            pd.DataFrame(
                {
                    "selection_date": [date] * 3,
                    "effective_date": [date + pd.offsets.BDay()] * 3,
                    "industry_code": ["801010"] * 3,
                    "component_ticker": ["000001", "000002", "000003"],
                    "component_rank": [1, 2, 3],
                    "target_weight": [1 / 3] * 3,
                    "avg_weight_90": [0.09, 0.08, 0.07],
                    "obs_ratio": [1.0, 1.0, 1.0],
                }
            ).to_parquet(component_dir / "202608.parquet", index=False)

            nav, components = MODULE.load_incremental_state(
                root, date, industry_codes=["801010"]
            )

        self.assertEqual(nav, {"801010": 123.0})
        self.assertEqual(components["component_ticker"].tolist(), ["000001", "000002", "000003"])

    def test_recalculated_date_replaces_all_old_assets_not_only_matching_keys(self):
        old = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-08-10"]),
                "industry_code": ["801010"],
                "asset_id": ["SYNTH_OLD"],
                "score": [np.nan],
            }
        )
        new = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-08-10"]),
                "industry_code": ["801010"],
                "asset_id": ["000001"],
                "score": [np.nan],
            }
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            MODULE.upsert_monthly_parquet(
                old, root, "trade_date", ["trade_date", "industry_code", "asset_id"]
            )
            MODULE.upsert_monthly_parquet(
                new,
                root,
                "trade_date",
                ["trade_date", "industry_code", "asset_id"],
                replace_existing_dates=True,
            )
            saved = pd.read_parquet(root / "year=2026/month=08/202608.parquet")

        self.assertEqual(saved["asset_id"].tolist(), ["000001"])

    def test_saved_leader_months_have_compatible_schema_when_ticker_is_all_null(self):
        leaders = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30", "2026-02-02"]),
                "effective_date": pd.to_datetime(["2026-02-02", "2026-02-03"]),
                "industry_code": ["801010", "801010"],
                "asset_id": ["SYNTH_SW_801010_20260130", "000001"],
                "asset_type": ["SYNTH", "REAL"],
                "stock_ticker": [pd.NA, "000001"],
                "selection_method": ["SYNTH_TOP3_EQUAL", "WEIGHT_THRESHOLD_DIRECT"],
                "selection_rank": [1, 1],
                "score": [np.nan, np.nan],
                "te": [np.nan, np.nan],
                "rho": [np.nan, np.nan],
                "avg_weight_90": [0.25, 0.20],
                "component_count": [3, 1],
            }
        )
        tables = {
            "leader_pool_daily": leaders,
            "synthetic_nav_daily": pd.DataFrame(),
            "synthetic_components_daily": pd.DataFrame(),
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            MODULE.save_dynamic_leader_tables(tables, root)
            saved = pd.read_parquet(sorted((root / "leader_pool_daily").rglob("*.parquet")))

        self.assertEqual(saved["stock_ticker"].dropna().tolist(), ["000001"])

    def test_all_synthetic_month_still_writes_stock_ticker_as_string(self):
        leaders = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30"]),
                "effective_date": pd.to_datetime(["2026-02-02"]),
                "industry_code": ["801010"],
                "asset_id": ["SYNTH_SW_801010_20260130"],
                "asset_type": ["SYNTH"],
                "stock_ticker": [pd.NA],
                "selection_method": ["SYNTH_TOP3_EQUAL"],
                "selection_rank": [1],
                "score": [np.nan],
                "te": [np.nan],
                "rho": [np.nan],
                "avg_weight_90": [0.25],
                "component_count": [3],
            }
        )
        tables = {
            "leader_pool_daily": leaders,
            "synthetic_nav_daily": pd.DataFrame(),
            "synthetic_components_daily": pd.DataFrame(),
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            MODULE.save_dynamic_leader_tables(tables, root)
            path = next((root / "leader_pool_daily").rglob("*.parquet"))
            field_type = str(pq.read_schema(path).field("stock_ticker").type)

        self.assertIn(field_type, {"string", "large_string"})

    def test_full_rebuild_removes_stale_months_and_rows(self):
        def leader_frame(dates, assets):
            count = len(dates)
            return pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(dates),
                    "effective_date": pd.to_datetime(dates),
                    "industry_code": ["801010"] * count,
                    "asset_id": assets,
                    "asset_type": ["REAL"] * count,
                    "stock_ticker": assets,
                    "selection_method": ["WEIGHT_THRESHOLD_DIRECT"] * count,
                    "selection_rank": [1] * count,
                    "score": [np.nan] * count,
                    "te": [np.nan] * count,
                    "rho": [np.nan] * count,
                    "avg_weight_90": [0.2] * count,
                    "component_count": [1] * count,
                }
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty_tables = {
                "synthetic_nav_daily": pd.DataFrame(),
                "synthetic_components_daily": pd.DataFrame(),
            }
            MODULE.save_dynamic_leader_tables(
                {"leader_pool_daily": leader_frame(["2026-01-30", "2026-02-02"], ["OLD1", "OLD2"]), **empty_tables},
                root,
            )
            MODULE.save_dynamic_leader_tables(
                {"leader_pool_daily": leader_frame(["2026-02-03"], ["NEW"]), **empty_tables},
                root,
                full_rebuild=True,
            )
            files = sorted((root / "leader_pool_daily").rglob("*.parquet"))
            saved = pd.read_parquet(files)

        self.assertEqual([path.name for path in files], ["202602.parquet"])
        self.assertEqual(saved["asset_id"].tolist(), ["NEW"])

    def test_monthly_upsert_replaces_same_primary_key_and_keeps_other_rows(self):
        old = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-08-10", "2026-08-11"]),
                "industry_code": ["801010", "801010"],
                "asset_id": ["000001", "000001"],
                "score": [0.4, 0.5],
            }
        )
        new = pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-08-11"]),
                "industry_code": ["801010"],
                "asset_id": ["000001"],
                "score": [0.9],
            }
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            MODULE.upsert_monthly_parquet(
                old, root, date_column="trade_date", primary_key=["trade_date", "industry_code", "asset_id"]
            )
            MODULE.upsert_monthly_parquet(
                new, root, date_column="trade_date", primary_key=["trade_date", "industry_code", "asset_id"]
            )
            saved = pd.read_parquet(root / "year=2026/month=08/202608.parquet")

        self.assertEqual(len(saved), 2)
        self.assertEqual(saved.loc[saved["trade_date"] == pd.Timestamp("2026-08-11"), "score"].item(), 0.9)

    def test_build_tables_outputs_real_leaders_and_daily_shadow_components(self):
        dates = pd.bdate_range("2026-01-01", periods=91)
        stocks = pd.concat(
            [
                pd.DataFrame(
                    {
                        "trade_date": dates,
                        "ticker": ticker,
                        "close": 100.0 + rank,
                        "pre_close_hfq": 100.0 + rank,
                        "is_open": 1,
                    }
                )
                for rank, ticker in enumerate(["000001", "000002", "000003", "000004", "000005"])
            ],
            ignore_index=True,
        )
        weights = pd.DataFrame(
            {
                "index_ticker": ["801010"] * 5,
                "effective_date": dates[0],
                "constituent_ticker": ["000001", "000002", "000003", "000004", "000005"],
                "weight": [40.0, 30.0, 20.0, 9.0, 1.0],
            }
        )

        tables = MODULE.build_dynamic_leader_tables(stocks, weights)

        first_day = dates[89]
        leaders = tables["leader_pool_daily"]
        components = tables["synthetic_components_daily"]
        self.assertEqual(leaders["trade_date"].min(), first_day)
        self.assertEqual(
            leaders.loc[leaders["trade_date"] == first_day, "stock_ticker"].tolist(),
            ["000001", "000002", "000003"],
        )
        self.assertEqual(
            components.loc[components["selection_date"] == first_day, "component_ticker"].tolist(),
            ["000001", "000002", "000003"],
        )

    def test_build_waits_for_90_days_of_weight_history(self):
        dates = pd.bdate_range("2026-01-01", periods=100)
        stocks = pd.concat(
            [
                pd.DataFrame(
                    {
                        "trade_date": dates,
                        "ticker": ticker,
                        "close": 100.0,
                        "pre_close_hfq": 100.0,
                        "is_open": 1,
                    }
                )
                for ticker in ["000001", "000002", "000003", "000004", "000005"]
            ],
            ignore_index=True,
        )
        weights = pd.DataFrame(
            {
                "index_ticker": ["801010"] * 5,
                "effective_date": dates[10],
                "constituent_ticker": ["000001", "000002", "000003", "000004", "000005"],
                "weight": [40.0, 30.0, 20.0, 9.0, 1.0],
            }
        )

        tables = MODULE.build_dynamic_leader_tables(stocks, weights)

        self.assertEqual(tables["leader_pool_daily"]["trade_date"].min(), dates[99])


if __name__ == "__main__":
    unittest.main()
