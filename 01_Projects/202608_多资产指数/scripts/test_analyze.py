import unittest
import sys
import tempfile
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze as analysis
import build_29_index_deck as deck
from analyze import (
    CUTOFF as ANALYSIS_CUTOFF,
    CHART_SPECS,
    INDIVIDUAL_CHART_SPECS,
    article_audit_field,
    individual_anomaly_summary,
    individual_period_bounds,
    individual_period_note,
    publication_marker_position,
    select_simplified_chinese_font,
)
from build_29_index_deck import (
    ARTICLE_CASE_EVALUATIONS,
    ARTICLE_SHARPE_FREQUENCY,
    CUTOFF as DECK_CUTOFF,
    FIGURE_NAMES,
    FIGURES,
    REPORT,
    RESEARCH_COLORS,
    _footnote,
    _case_conclusion,
    _image_markdown,
    article_style_judgement,
    calculate_universe_metrics,
    clean_index_daily,
    configure_charts,
    markdown_table,
    project_comment,
    style_axes,
    validate_markdown_links,
    validate_slide_titles,
)


class ChartLogicTests(unittest.TestCase):
    def test_source_workbooks_are_loaded_from_data_directory(self):
        source_workbooks = [
            analysis.RAW_FILE,
            analysis.HAND_FILE,
            deck.RAW_FILE,
            deck.GT01_SUPPLEMENT_FILE,
        ]

        for workbook_path in source_workbooks:
            with self.subTest(workbook=workbook_path.name):
                self.assertEqual(workbook_path.parent.name, "data")
                self.assertTrue(workbook_path.is_file())
                with pd.ExcelFile(workbook_path) as workbook:
                    self.assertGreater(len(workbook.sheet_names), 0)

    def test_universe_markdown_table_lists_all_29_indices_once_by_analysis_group(self):
        rows = []
        groups = (
            ["19只发布前后比较"] * 19
            + ["3只公开运行记录"] * 3
            + ["7只停更/数据不足"] * 7
        )
        for sequence, group in enumerate(groups, start=1):
            rows.append(
                {
                    "文章序号": sequence,
                    "Wind代码": f"IDX{sequence:02d}.WI",
                    "证券简称": f"测试指数{sequence:02d}",
                    "公众号分组": group,
                }
            )

        self.assertTrue(
            hasattr(deck, "_universe_markdown_table"),
            "生成程序尚未实现29只研究样本的分组清单表",
        )
        table = deck._universe_markdown_table(pd.DataFrame(rows))

        self.assertIn("发布前后比较①", table)
        self.assertIn("发布前后比较②", table)
        self.assertIn("公开运行记录（3只）", table)
        self.assertIn("停更/数据不足（7只）", table)
        for sequence in range(1, 30):
            self.assertEqual(table.count(f"IDX{sequence:02d}.WI"), 1)

    def test_sample_structure_figure_uses_two_composition_rows_without_wind_coverage(self):
        metrics = pd.DataFrame(
            {
                "公众号分组": ["19只发布前后比较"] * 19
                + ["3只公开运行记录"] * 3
                + ["7只停更/数据不足"] * 7,
                "收益差": [0.03] * 19 + [float("nan")] * 10,
                "复算判断": ["过拟合"] * 10
                + ["基本一致"] * 8
                + ["样本外更好"]
                + ["—"] * 10,
            }
        )

        self.assertTrue(
            hasattr(deck, "make_sample_structure_figure"),
            "样本结构图尚未拆分为可独立验证的双横向堆叠条实现",
        )
        fig = deck.make_sample_structure_figure(metrics)
        try:
            self.assertEqual(len(fig.axes), 1)
            ax = fig.axes[0]
            self.assertEqual(
                [label.get_text() for label in ax.get_yticklabels()],
                ["29只母样本", "19只可比样本"],
            )
            all_text = " ".join(text.get_text() for text in ax.texts)
            self.assertNotIn("Wind行情覆盖", all_text)
            self.assertIn("前后比较", all_text)
            self.assertIn("衰减>2pct", all_text)
            self.assertIn("19只", all_text)
            self.assertIn("10只", all_text)
            self.assertEqual(len(ax.patches), 6)
        finally:
            plt.close(fig)

    def test_gt01_supplement_replaces_partial_history_and_preserves_other_indices(self):
        existing = pd.DataFrame(
            {
                "Wind代码": ["OTHER.WI", "GT01.WI"],
                "证券简称": ["其他指数", "国泰全天候低波"],
                "日期": pd.to_datetime(["2020-01-02", "2025-03-17"]),
                "最早交易日期到2026年8月11日每日收盘价": [100.0, 2222.5809],
                "交易币种": ["CNY", "CNY"],
                "最早交易日期": pd.to_datetime(["2020-01-02", "2025-03-17"]),
                "最早交易日期到2026年8月11日每日涨跌幅(%)": [0.0, 0.2546],
                "最早交易日期到2026年8月11日每日成交量(股)": [None, None],
                "最后有效更新日期": [pd.NaT, pd.NaT],
                "数据状态": ["正常更新", None],
                "提取日期": pd.to_datetime(["2026-08-12", "2026-08-12"]),
                "数据来源": ["Wind金融终端", "Wind金融终端"],
            }
        )
        supplement = pd.DataFrame(
            {
                "Wind代码": ["GT01.WI", "GT01.WI", "GT01.WI"],
                "证券简称": ["国泰全天候低波"] * 3,
                "日期": pd.to_datetime(["2015-01-05", "2015-01-06", "2026-08-11"]),
                "收盘价": [999.7, 1005.3317, 2463.9214],
                "交易币种": ["CNY"] * 3,
                "成交量(股)": [None, None, None],
            }
        )

        self.assertTrue(
            hasattr(deck, "merge_gt01_daily_rows"),
            "生成程序尚未实现GT01补充行情合并逻辑",
        )
        merged = deck.merge_gt01_daily_rows(
            existing,
            supplement,
            extraction_date=pd.Timestamp("2026-08-17"),
        )

        other = merged.loc[merged["Wind代码"] == "OTHER.WI"]
        gt01 = merged.loc[merged["Wind代码"] == "GT01.WI"].sort_values("日期")
        self.assertEqual(len(other), 1)
        self.assertEqual(len(gt01), 3)
        self.assertEqual(gt01["日期"].iloc[0], pd.Timestamp("2015-01-05"))
        self.assertEqual(gt01["日期"].iloc[-1], pd.Timestamp("2026-08-11"))
        self.assertAlmostEqual(
            gt01["最早交易日期到2026年8月11日每日收盘价"].iloc[-1],
            2463.9214,
        )
        self.assertEqual(gt01["最早交易日期"].nunique(), 1)
        self.assertEqual(gt01["最早交易日期"].iloc[0], pd.Timestamp("2015-01-05"))
        self.assertEqual(gt01["数据状态"].unique().tolist(), ["正常更新"])
        self.assertEqual(gt01["数据来源"].unique().tolist(), ["Wind金融终端（GT01单独补充）"])
        self.assertAlmostEqual(
            gt01["最早交易日期到2026年8月11日每日涨跌幅(%)"].iloc[1],
            (1005.3317 / 999.7 - 1) * 100,
        )

    def test_reconcile_article_universe_restores_callwe_placeholder_without_copying_callw_prices(self):
        source_codes = [code for code in deck.ARTICLE_ORDER if code != "CALLWE.WI"]
        books = {
            "Index_Info": pd.DataFrame(
                {"Wind代码": source_codes, "证券简称": source_codes}
            ),
            "Index_Daily": pd.DataFrame(
                {
                    "Wind代码": ["CALLW.WI", "CALLW.WI"],
                    "证券简称": ["高华中国全天候", "高华中国全天候"],
                    "日期": pd.to_datetime(["2026-08-04", "2026-08-05"]),
                    "收盘价": [1200.0, 1201.0],
                }
            ),
            "Selection_Audit": pd.DataFrame(
                {"Wind代码": source_codes, "证券简称": source_codes}
            ),
        }

        self.assertTrue(
            hasattr(deck, "reconcile_article_universe"),
            "生成程序尚未实现29只文章样本与28只Wind行情的对账逻辑",
        )
        reconciled = deck.reconcile_article_universe(books)

        self.assertEqual(set(reconciled["Index_Info"]["Wind代码"]), set(deck.ARTICLE_ORDER))
        callwe = reconciled["Index_Info"].set_index("Wind代码").loc["CALLWE.WI"]
        self.assertEqual(callwe["证券简称"], "高华中国全天候增强")
        self.assertIn("Wind未检索", str(callwe["数据来源"]))
        self.assertEqual(callwe["数据状态"], "停更/无数据")
        self.assertNotIn("CALLWE.WI", set(reconciled["Index_Daily"]["Wind代码"]))
        self.assertEqual(
            reconciled["Index_Daily"].loc[
                reconciled["Index_Daily"]["Wind代码"] == "CALLW.WI", "收盘价"
            ].tolist(),
            [1200.0, 1201.0],
        )
        callwe_audit = reconciled["Selection_Audit"].set_index("Wind代码").loc["CALLWE.WI"]
        self.assertEqual(callwe_audit["异常状态"], "停更/无数据")

        metrics = calculate_universe_metrics(
            reconciled["Index_Info"],
            {},
            pd.DataFrame(),
        ).set_index("Wind代码")
        self.assertEqual(metrics.loc["CALLWE.WI", "数据状态"], "停更/无数据")
        self.assertEqual(metrics.loc["CALLWE.WI", "公众号分组"], "7只停更/数据不足")
        self.assertEqual(metrics.loc["CALLWE.WI", "全历史观测数"], 0)
        self.assertEqual(
            metrics.loc["CALLWE.WI", "项目评价"],
            "确认停更且无行情；保留在29只母样本中，不进入绩效计算。",
        )

    def test_all_analysis_pipelines_use_article_cutoff(self):
        expected = pd.Timestamp("2026-08-05")
        self.assertEqual(ANALYSIS_CUTOFF, expected)
        self.assertEqual(DECK_CUTOFF, expected)

    def test_case_conclusion_uses_recalculated_row_instead_of_stale_numbers(self):
        row = pd.Series(
            {
                "发布前年化收益": 0.101,
                "发布后年化收益": 0.042,
                "发布前夏普": 1.23,
                "发布后夏普": 0.34,
                "发布前年化波动": 0.056,
                "发布后年化波动": 0.123,
                "发布前最大回撤": -0.044,
                "发布后最大回撤": -0.087,
                "发布后年数": 0.71,
            }
        )
        _, conclusion = _case_conclusion("GALLW.WI", row)
        self.assertIn("收益由10.1%降至4.2%", conclusion)
        self.assertIn("夏普由1.23降至0.34", conclusion)
        self.assertIn("波动由5.6%升至12.3%", conclusion)
        self.assertIn("发布后仅0.71年", conclusion)

    def test_markdown_deck_keeps_generated_images_beside_report(self):
        self.assertEqual(FIGURES.parent, REPORT.parent)
        path = FIGURES / "example.png"
        self.assertEqual(_image_markdown(path), "![w:720](./figures/example.png)")

    def test_research_chart_theme_renders_white_page_and_near_white_axes(self):
        configure_charts()
        fig, ax = plt.subplots()

        self.assertEqual(mpl.colors.to_rgba(fig.get_facecolor()), mpl.colors.to_rgba("#FFFFFF"))
        self.assertEqual(mpl.colors.to_rgba(ax.get_facecolor()), mpl.colors.to_rgba("#FAFAFA"))
        self.assertEqual(mpl.colors.to_rgba(mpl.rcParams["savefig.facecolor"]), mpl.colors.to_rgba("#FFFFFF"))
        self.assertFalse(mpl.rcParams["savefig.transparent"])
        self.assertFalse(mpl.rcParams["legend.frameon"])
        plt.close(fig)

    def test_chart_footnote_can_disclose_non_wind_source(self):
        fig = plt.figure()
        _footnote(fig, "数据来源：Wind、公众号原文")
        self.assertEqual(fig.texts[-1].get_text(), "数据来源：Wind、公众号原文")
        plt.close(fig)

    def test_style_axes_hides_heavy_spines_and_uses_light_grid(self):
        configure_charts()
        fig, ax = plt.subplots()
        style_axes(ax, "y")

        self.assertFalse(ax.spines["top"].get_visible())
        self.assertFalse(ax.spines["right"].get_visible())
        self.assertLessEqual(ax.spines["left"].get_linewidth(), 0.8)
        self.assertEqual(mpl.colors.to_rgba(ax.spines["left"].get_edgecolor()), mpl.colors.to_rgba("#BCC4CA"))
        self.assertTrue(any(line.get_visible() for line in ax.get_ygridlines()))
        self.assertFalse(any(line.get_visible() for line in ax.get_xgridlines()))
        plt.close(fig)

    def test_research_palette_removes_previous_bright_orange(self):
        self.assertEqual(RESEARCH_COLORS["primary"], "#355F78")
        self.assertEqual(RESEARCH_COLORS["negative"], "#A85B63")
        self.assertNotIn("#D9922E", RESEARCH_COLORS.values())

    def test_direction_colors_follow_domestic_market_convention(self):
        self.assertEqual(RESEARCH_COLORS["up"], "#A85B63")
        self.assertEqual(RESEARCH_COLORS["down"], "#587E78")
        self.assertEqual(RESEARCH_COLORS["better"], "#A85B63")
        self.assertEqual(RESEARCH_COLORS["worse"], "#587E78")

    def test_reconstructed_deck_uses_joint_change_and_sensitivity_charts(self):
        self.assertEqual(len(FIGURE_NAMES), 10)
        self.assertEqual(FIGURE_NAMES[0], "01_样本结构与复算范围.png")
        self.assertEqual(FIGURE_NAMES[1], "02_收益与夏普联合变化.png")
        self.assertEqual(FIGURE_NAMES[2], "03_收益衰减多维诊断.png")
        self.assertEqual(FIGURE_NAMES[3], "04_原文值与统一复算.png")
        self.assertEqual(FIGURE_NAMES[-1], "10_收益衰减敏感性.png")
        self.assertNotIn("02_全景判断分布.png", FIGURE_NAMES)
        banned = ("完整指标表", "最终评价", "过拟合机制", "个案页")
        self.assertFalse(any(any(word in name for word in banned) for name in FIGURE_NAMES))

    def test_focus_cases_preserve_article_evaluation_and_mixed_frequency_note(self):
        self.assertEqual(set(ARTICLE_CASE_EVALUATIONS), {"CI011800.WI", "CICSF040.WI", "CI011001.WI", "GALLW.WI"})
        self.assertEqual(ARTICLE_SHARPE_FREQUENCY[("CICSF040.WI", "all")], "月频")

    def test_slide_titles_use_objective_statements_instead_of_questions(self):
        markdown = """# 指数筛选与方法论

# [全景] 发布后收益衰减幅度前十
"""
        self.assertEqual(
            validate_slide_titles(markdown),
            ["指数筛选与方法论", "[全景] 发布后收益衰减幅度前十"],
        )
        with self.assertRaisesRegex(AssertionError, "客观陈述式"):
            validate_slide_titles("# 收益衰减最大的十只是谁？\n")
        with self.assertRaisesRegex(AssertionError, "公众号"):
            validate_slide_titles("# 公众号如何筛出29只指数\n")

    def test_markdown_table_is_native_markdown(self):
        text = markdown_table(pd.DataFrame([{"A": 1, "B": 2}]), ["A", "B"])
        self.assertIn("| A | B |", text)
        self.assertNotIn("<table", text)

    def test_article_style_judgement_uses_article_return_decay_logic(self):
        self.assertEqual(article_style_judgement({"收益差": 0.025}), "过拟合")
        self.assertEqual(article_style_judgement({"收益差": 0.002}), "基本一致")
        self.assertEqual(article_style_judgement({"收益差": -0.030}), "样本外更好")

    def test_project_comment_keeps_short_sample_boundary_in_text(self):
        text = project_comment({"复算判断": "过拟合", "发布后年数": 0.7, "数据状态": "正常"})
        self.assertIn("不足1年", text)
        self.assertNotIn("确认过拟合", text)

    def test_universe_metrics_share_anchor_and_do_not_invent_pre_period(self):
        dates = pd.to_datetime(["2020-01-02", "2020-06-30", "2021-01-04"])
        info = pd.DataFrame(
            {
                "Wind代码": ["X.WI", "Y.WI"],
                "证券简称": ["有回溯", "无回溯"],
                "发布日期": ["2020-07-01", "2020-01-02"],
                "基期": ["2020-01-02", "2020-01-02"],
                "收益处理方式": ["价格指数", "价格指数"],
            }
        )
        series = {
            "X.WI": pd.Series([100.0, 110.0, 121.0], index=dates),
            "Y.WI": pd.Series([100.0, 102.0, 105.0], index=dates),
        }
        audit = pd.DataFrame(
            {
                "Wind代码": ["X.WI", "Y.WI"],
                "数据状态": ["正常更新", "正常更新"],
                "计算截止日": [dates[-1], dates[-1]],
            }
        )

        result = calculate_universe_metrics(info, series, audit)
        x = result.set_index("Wind代码").loc["X.WI"]
        y = result.set_index("Wind代码").loc["Y.WI"]

        self.assertEqual(x["发布切分锚点"], pd.Timestamp("2020-06-30"))
        self.assertEqual(x["发布前截止日"], x["发布后起始日"])
        self.assertTrue(pd.isna(y["发布前年化收益"]))
        self.assertEqual(y["复算判断"], "暂不判断")

    def test_markdown_link_validation_checks_all_local_images(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report_dir = root / "reports"
            figure_dir = root / "figures"
            report_dir.mkdir()
            figure_dir.mkdir()
            (figure_dir / "one.png").write_bytes(b"png")
            markdown = "# test\n\n![](../figures/one.png)\n"
            links = validate_markdown_links(markdown, report_dir / "deck.md")
            self.assertEqual(links, [(figure_dir / "one.png").resolve()])

    def test_terminal_forward_fill_is_removed_but_first_flat_point_is_kept(self):
        daily = pd.DataFrame(
            {
                "Wind代码": ["X.WI"] * 5,
                "证券简称": ["测试指数"] * 5,
                "日期": pd.date_range("2020-01-01", periods=5),
                "收盘价": [100.0, 101.0, 102.0, 102.0, 102.0],
                "数据状态": ["停更后前向填充(停更于2020-01-03)"] * 5,
                "最后有效更新日期": ["2020-01-03"] * 5,
            }
        )

        cleaned, audit = clean_index_daily(daily, pd.Timestamp("2020-01-05"))

        self.assertEqual(cleaned["日期"].max(), pd.Timestamp("2020-01-03"))
        self.assertEqual(int(audit.loc[0, "删除的前向填充行数"]), 2)

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
