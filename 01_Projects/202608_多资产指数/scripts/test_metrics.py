import math
import unittest

import numpy as np
import pandas as pd

from scripts.metrics import (
    annual_returns,
    best_year_counterfactual,
    calendar_years,
    closest_candidate,
    maximum_drawdown,
    moving_block_bootstrap_return_delta,
    performance_metrics,
    return_method_candidates,
    sharpe_method_candidates,
    split_at_publication,
    stress_window_metrics,
    summarize_rolling_metric,
    volatility_method_candidates,
)


class MetricTests(unittest.TestCase):
    def test_calendar_years_uses_elapsed_calendar_days(self):
        self.assertAlmostEqual(
            calendar_years(pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01")),
            366 / 365.2425,
        )

    def test_cagr_uses_calendar_time_not_observation_count(self):
        prices = pd.Series(
            [100.0, 110.0],
            index=pd.to_datetime(["2020-01-01", "2021-01-01"]),
        )
        result = performance_metrics(prices, annual_risk_free_rate=0.0)
        expected = 1.1 ** (365.2425 / 366) - 1
        self.assertAlmostEqual(result["annual_return"], expected)

    def test_maximum_drawdown_dates_and_depth_are_exact(self):
        prices = pd.Series(
            [100.0, 120.0, 90.0, 108.0, 121.0],
            index=pd.to_datetime(
                ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04", "2020-01-05"]
            ),
        )
        result = maximum_drawdown(prices)
        self.assertAlmostEqual(result["max_drawdown"], -0.25)
        self.assertEqual(result["peak_date"], pd.Timestamp("2020-01-02"))
        self.assertEqual(result["trough_date"], pd.Timestamp("2020-01-03"))
        self.assertEqual(result["recovery_date"], pd.Timestamp("2020-01-05"))

    def test_publication_point_is_shared_by_pre_and_post_segments(self):
        prices = pd.Series(
            [100.0, 101.0, 102.0, 103.0],
            index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"]),
        )
        pre, post, anchor = split_at_publication(prices, pd.Timestamp("2020-01-04"))
        self.assertEqual(anchor, pd.Timestamp("2020-01-03"))
        self.assertEqual(pre.index[-1], anchor)
        self.assertEqual(post.index[0], anchor)
        self.assertEqual(len(pre), 3)
        self.assertEqual(len(post), 2)

    def test_daily_sharpe_uses_arithmetic_daily_excess_return(self):
        returns = np.array([0.01, -0.005, 0.004, 0.002])
        prices = pd.Series(
            100 * np.r_[1.0, np.cumprod(1 + returns)],
            index=pd.date_range("2020-01-01", periods=5, freq="B"),
        )
        result = performance_metrics(prices, annual_risk_free_rate=0.0)
        expected = returns.mean() / returns.std(ddof=1) * math.sqrt(252)
        self.assertAlmostEqual(result["sharpe_daily"], expected)

    def test_annual_returns_use_prior_year_end_as_the_next_year_base(self):
        prices = pd.Series(
            [100.0, 110.0, 121.0],
            index=pd.to_datetime(["2020-01-02", "2020-12-31", "2021-12-31"]),
        )
        result = annual_returns(prices)
        self.assertAlmostEqual(result.loc[2020], 0.10)
        self.assertAlmostEqual(result.loc[2021], 0.10)

    def test_block_bootstrap_is_reproducible_and_reports_probability(self):
        pre = pd.Series(np.full(60, 0.001))
        post = pd.Series(np.full(60, 0.002))
        one = moving_block_bootstrap_return_delta(pre, post, block_size=10, simulations=100, seed=7)
        two = moving_block_bootstrap_return_delta(pre, post, block_size=10, simulations=100, seed=7)
        self.assertEqual(one, two)
        self.assertEqual(one["probability_post_gt_pre"], 1.0)
        self.assertGreater(one["ci_low"], 0)

    def test_stress_window_reports_endpoint_return_and_in_window_drawdown(self):
        prices = pd.Series(
            [100.0, 120.0, 90.0, 110.0],
            index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"]),
        )
        result = stress_window_metrics(prices, "2020-01-01", "2020-01-06")
        self.assertEqual(result["actual_start"], pd.Timestamp("2020-01-01"))
        self.assertEqual(result["actual_end"], pd.Timestamp("2020-01-06"))
        self.assertAlmostEqual(result["window_return"], 0.10)
        self.assertAlmostEqual(result["window_max_drawdown"], -0.25)

    def test_rolling_summary_reports_extremes_latest_and_threshold_shares(self):
        values = pd.Series(
            [np.nan, -0.5, 0.5, 1.5],
            index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"]),
        )
        result = summarize_rolling_metric(values)
        self.assertEqual(result["observations"], 3)
        self.assertEqual(result["minimum_date"], pd.Timestamp("2020-01-02"))
        self.assertEqual(result["maximum_date"], pd.Timestamp("2020-01-06"))
        self.assertAlmostEqual(result["minimum"], -0.5)
        self.assertAlmostEqual(result["maximum"], 1.5)
        self.assertAlmostEqual(result["latest"], 1.5)
        self.assertAlmostEqual(result["share_above_zero"], 2 / 3)
        self.assertAlmostEqual(result["share_above_one"], 1 / 3)

    def test_best_year_counterfactual_sets_best_calendar_year_returns_to_zero(self):
        prices = pd.Series(
            [100.0, 110.0, 132.0, 145.2],
            index=pd.to_datetime(["2020-01-02", "2020-12-31", "2021-12-31", "2022-12-30"]),
        )
        result = best_year_counterfactual(prices)
        self.assertEqual(result["best_year"], 2021)
        self.assertAlmostEqual(result["best_year_return"], 0.20)
        self.assertAlmostEqual(result["counterfactual_total_return"], 0.21)
        self.assertLess(result["counterfactual_annual_return"], result["full_annual_return"])

    def test_return_candidate_grid_contains_calendar_and_trading_day_methods(self):
        prices = pd.Series(
            [100.0, 110.0, 121.0],
            index=pd.to_datetime(["2020-01-01", "2020-12-31", "2021-12-31"]),
        )
        result = return_method_candidates(prices)
        self.assertIn("实际日历CAGR", result)
        self.assertIn("252交易日几何年化", result)
        self.assertIn("日收益算术均值×252", result)
        self.assertAlmostEqual(result["实际日历CAGR"], 0.10, places=3)

    def test_sharpe_candidate_grid_uses_explicit_frequency_and_risk_free_rate(self):
        returns = np.array([0.01, -0.005, 0.004, 0.002, 0.003])
        prices = pd.Series(
            100 * np.r_[1.0, np.cumprod(1 + returns)],
            index=pd.date_range("2020-01-01", periods=6, freq="B"),
        )
        result = sharpe_method_candidates(prices, risk_free_rates=(0.0, 0.015))
        self.assertIn("日频算术夏普|Rf=0.0%", result)
        self.assertIn("日频算术夏普|Rf=1.5%", result)
        expected = returns.mean() / returns.std(ddof=1) * math.sqrt(252)
        self.assertAlmostEqual(result["日频算术夏普|Rf=0.0%"], expected)

    def test_volatility_candidate_grid_includes_monthly_annualized_volatility(self):
        prices = pd.Series(
            [100.0, 101.0, 99.0, 103.0],
            index=pd.to_datetime(["2020-01-31", "2020-02-28", "2020-03-31", "2020-04-30"]),
        )
        result = volatility_method_candidates(prices)
        monthly = prices.pct_change(fill_method=None).dropna()
        self.assertAlmostEqual(result["月频标准差×√12"], monthly.std(ddof=1) * math.sqrt(12))

    def test_closest_candidate_returns_name_value_and_absolute_gap(self):
        result = closest_candidate({"方法A": 1.0, "方法B": 1.4, "空值": np.nan}, target=1.3)
        self.assertEqual(result["method"], "方法B")
        self.assertAlmostEqual(result["value"], 1.4)
        self.assertAlmostEqual(result["absolute_gap"], 0.1)


if __name__ == "__main__":
    unittest.main()
