import unittest
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import (
    CHART_SPECS,
    INDIVIDUAL_CHART_SPECS,
    article_audit_field,
    individual_anomaly_summary,
    individual_period_bounds,
    individual_period_note,
    publication_marker_position,
    select_simplified_chinese_font,
)


class ChartLogicTests(unittest.TestCase):
    def test_article_audit_uses_one_common_field_per_metric(self):
        self.assertEqual(article_audit_field("annual_return"), "annual_return")
        self.assertEqual(article_audit_field("sharpe"), "sharpe_daily_rf1.5")

    def test_article_audit_chart_is_explicitly_labeled_as_common_method(self):
        self.assertEqual(CHART_SPECS["article_audit"][0], "公众号统一口径复算")

    def test_font_selection_prefers_pingfang_sc_and_rejects_hk(self):
        family, font_path = select_simplified_chinese_font()
        self.assertIn(family, {"PingFang SC", "苹方-简"})
        self.assertNotIn("HK", family.upper())
        self.assertEqual(font_path.name, "PingFangSC-Regular.ttf")

    def test_all_chart_specs_use_short_comparison_titles_and_names(self):
        self.assertEqual(len(CHART_SPECS), 12)
        self.assertEqual(CHART_SPECS["rolling_sharpe"], ("4只指数滚动夏普比较", "05_滚动夏普比较.png"))
        for title, filename in CHART_SPECS.values():
            self.assertLessEqual(len(title), 18)
            self.assertNotIn("：", title)
            self.assertRegex(filename, r"^\d{2}_[^：]{2,16}\.png$")

    def test_individual_chart_specs_cover_each_index_once(self):
        self.assertEqual(
            INDIVIDUAL_CHART_SPECS,
            {
                "CI011800.WI": "13_CI011800个案走势.png",
                "CICSF040.WI": "14_CICSF040个案走势.png",
                "CI011001.WI": "15_CI011001个案走势.png",
                "GALLW.WI": "16_GALLW个案走势.png",
            },
        )

    def test_individual_period_bounds_omit_pre_period_when_publication_is_first_date(self):
        dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
        pre, post = individual_period_bounds(dates, pd.Timestamp("2020-01-02"))
        self.assertIsNone(pre)
        self.assertEqual(post, (pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-06")))

    def test_individual_period_bounds_split_at_last_observation_before_publication(self):
        dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
        pre, post = individual_period_bounds(dates, pd.Timestamp("2020-01-05"))
        self.assertEqual(pre, (pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-03")))
        self.assertEqual(post, (pd.Timestamp("2020-01-03"), pd.Timestamp("2020-01-06")))

    def test_individual_period_note_does_not_claim_missing_pre_period(self):
        self.assertEqual(individual_period_note(False), "本指数无发布前回溯段；浅色=发布后运行期；黑点=全历史最大回撤谷值；数据：Wind")
        self.assertIn("灰色=发布前回溯期", individual_period_note(True))

    def test_individual_anomaly_summary_uses_pre_post_metrics_without_causal_claims(self):
        metrics = pd.DataFrame(
            [
                {"指数代码": "CI011001.WI", "区间": "发布前回溯期", "annual_return": 0.0841, "annual_volatility": 0.0431},
                {"指数代码": "CI011001.WI", "区间": "发布后运行期", "annual_return": 0.0930, "annual_volatility": 0.0422},
                {"指数代码": "GALLW.WI", "区间": "发布前回溯期", "annual_return": 0.1163, "annual_volatility": 0.0667},
                {"指数代码": "GALLW.WI", "区间": "发布后运行期", "annual_return": 0.0666, "annual_volatility": 0.1144},
            ]
        )
        self.assertEqual(individual_anomaly_summary("CI011001.WI", metrics), "发布后年化仅提高0.89个百分点")
        self.assertEqual(individual_anomaly_summary("GALLW.WI", metrics), "发布后波动由6.67%升至11.44%")

    def test_publication_marker_includes_publication_equal_to_first_observation(self):
        prices = pd.Series(
            [100.0, 101.0, 102.0],
            index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
        )
        date, value = publication_marker_position(prices, pd.Timestamp("2020-01-02"))
        self.assertEqual(date, pd.Timestamp("2020-01-02"))
        self.assertEqual(value, 100.0)

    def test_publication_marker_uses_last_observation_on_or_before_nontrading_date(self):
        prices = pd.Series(
            [100.0, 101.0, 102.0],
            index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
        )
        date, value = publication_marker_position(prices, pd.Timestamp("2020-01-05"))
        self.assertEqual(date, pd.Timestamp("2020-01-03"))
        self.assertEqual(value, 101.0)


if __name__ == "__main__":
    unittest.main()
