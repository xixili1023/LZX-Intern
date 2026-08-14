import sys
import unittest
from collections import Counter
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

from review_uqer_approved_candidates import (  # noqa: E402
    audit_candidate,
    load_approval_workbook,
    materialize_candidate_specs,
    merge_approval_records,
    rank_candidate,
)


class MergeApprovalRecordsTest(unittest.TestCase):
    def test_real_workbooks_preserve_all_colored_decisions(self):
        desktop = Path("/Users/lizhexi/Desktop")
        full = load_approval_workbook(desktop / "UQER指标完整候选审核表.xlsx", "full")
        priority = load_approval_workbook(desktop / "UQER指标优先审核表.xlsx", "priority")

        self.assertEqual(len(full), 94)
        self.assertEqual(Counter(r["approval_color"] for r in full), {"yellow": 55, "green": 33, "blue": 6})
        self.assertEqual(len(priority), 39)
        self.assertEqual(Counter(r["approval_color"] for r in priority), {"yellow": 32, "green": 5, "blue": 2})

    def test_priority_color_overrides_duplicate_full_record(self):
        full = [
            {
                "wind_code": "W1",
                "uqer_indic_id": "U1",
                "approval_color": "green",
                "workbook": "full",
            }
        ]
        priority = [
            {
                "wind_code": "W1",
                "uqer_indic_id": "U1",
                "approval_color": "yellow",
                "workbook": "priority",
            }
        ]

        merged = merge_approval_records(full, priority)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["approval_color"], "yellow")
        self.assertEqual(merged[0]["approval_source"], "priority")

    def test_unique_rows_from_both_workbooks_are_retained(self):
        full = [{"wind_code": "W1", "uqer_indic_id": "U1", "approval_color": "yellow"}]
        priority = [{"wind_code": "W2", "uqer_indic_id": "U2", "approval_color": "blue"}]

        merged = merge_approval_records(full, priority)

        self.assertEqual({(r["wind_code"], r["uqer_indic_id"]) for r in merged}, {("W1", "U1"), ("W2", "U2")})

    def test_same_indicator_pair_is_retained_for_distinct_mapping_rows(self):
        full = [
            {"mapping_row_id": "10", "industry_code": "801950", "wind_code": "W1", "uqer_indic_id": "U1", "approval_color": "yellow"},
            {"mapping_row_id": "122", "industry_code": "801160", "wind_code": "W1", "uqer_indic_id": "U1", "approval_color": "yellow"},
        ]

        merged = merge_approval_records(full, [])

        self.assertEqual(len(merged), 2)


class AuditCandidateTest(unittest.TestCase):
    def test_national_target_rejects_unrelated_foreign_region(self):
        record = {
            "wind_name": "中国:产量:原油",
            "uqer_name": "日本:产量:原油",
            "uqer_region": "日本",
            "approval_color": "green",
            "function_type": "产量",
            "calculation_type": "当期值",
            "uqer_stat_type": "当期值",
            "uqer_frequency": "月",
            "uqer_unit": "千升",
        }

        audited = audit_candidate(record)

        self.assertEqual(audited["review_status"], "不可替代")
        self.assertIn("地区冲突", audited["risk_flags"])

    def test_monthly_exact_object_outranks_daily_wrong_statistic(self):
        target = {"wind_name": "中国:产量:精炼铜", "function_type": "产量", "calculation_type": "当期值"}
        monthly_exact = {
            "uqer_name": "产量:精炼铜:当月值",
            "uqer_region": "中国",
            "uqer_frequency": "月",
            "uqer_stat_type": "当期值",
            "uqer_begin_date": "2000-01-01",
            "uqer_end_date": "2026-08-01",
            "uqer_is_update": "1",
        }
        daily_wrong = {
            "uqer_name": "现货价:精炼铜",
            "uqer_region": "中国",
            "uqer_frequency": "日",
            "uqer_stat_type": "当期值",
            "uqer_begin_date": "2000-01-01",
            "uqer_end_date": "2026-08-01",
            "uqer_is_update": "1",
        }

        self.assertGreater(rank_candidate(target, monthly_exact), rank_candidate(target, daily_wrong))

    def test_national_monthly_outranks_regional_daily_proxy(self):
        target = {"wind_name": "中国:水泥产量", "function_type": "产量", "calculation_type": "当期值"}
        national = {
            "uqer_name": "产量:水泥:当月值",
            "uqer_region": "中国",
            "uqer_frequency": "月",
            "uqer_stat_type": "当期值",
            "uqer_begin_date": "2000-01-01",
            "uqer_end_date": "2026-08-01",
            "uqer_is_update": "1",
        }
        regional = {
            "uqer_name": "价格:水泥:杭州市",
            "uqer_region": "浙江省杭州市",
            "uqer_frequency": "日",
            "uqer_stat_type": "当期值",
            "uqer_begin_date": "2015-01-01",
            "uqer_end_date": "2026-08-01",
            "uqer_is_update": "1",
        }

        self.assertGreater(rank_candidate(target, national), rank_candidate(target, regional))

    def test_blue_record_is_kept_only_as_supplementary(self):
        record = {
            "wind_name": "中国:价格:螺纹钢",
            "uqer_name": "螺纹钢期货结算价",
            "uqer_region": "中国",
            "approval_color": "blue",
            "function_type": "价格",
            "calculation_type": "原始值",
            "uqer_stat_type": "当期值",
            "uqer_frequency": "日",
            "uqer_unit": "元/吨",
        }

        audited = audit_candidate(record)

        self.assertEqual(audited["review_status"], "仅补充")

    def test_stainless_wire_cannot_replace_total_stainless_export(self):
        audited = audit_candidate(
            {
                "mapping_row_id": "78",
                "uqer_indic_id": "2040201927",
                "wind_name": "中国:出口数量:不锈钢:当月值",
                "uqer_name": "出口数量:不锈钢丝(7223):当月值",
                "approval_color": "yellow",
            }
        )

        self.assertEqual(audited["review_status"], "仅补充")
        self.assertIn("HS 7223", audited["review_reason"])

    def test_change_rate_cannot_replace_rebar_price_level(self):
        audited = audit_candidate(
            {
                "mapping_row_id": "73",
                "uqer_indic_id": "1040005377",
                "wind_name": "中国:价格:螺纹钢(HRB400E,20mm)",
                "uqer_name": "生产资料价格:钢材:螺纹钢:Φ20mmHRB400E:环比",
                "approval_color": "yellow",
            }
        )

        self.assertEqual(audited["review_status"], "仅补充")
        self.assertIn("环比", audited["review_reason"])

    def test_electrolytic_aluminum_output_cannot_replace_capacity(self):
        audited = audit_candidate(
            {
                "mapping_row_id": "23",
                "uqer_indic_id": "1020008684",
                "wind_name": "中国:产能:电解铝:当月值",
                "uqer_name": "产量:原铝(电解铝):当月值",
                "approval_color": "green",
            }
        )

        self.assertEqual(audited["review_status"], "不可替代")

    def test_exact_power_investment_mapping_is_confirmed(self):
        audited = audit_candidate(
            {
                "mapping_row_id": "164",
                "uqer_indic_id": "2020104977",
                "wind_name": "中国:电源基本建设投资完成额:累计同比",
                "uqer_name": "电源工程投资完成:累计同比",
                "approval_color": "green",
            }
        )

        self.assertEqual(audited["review_status"], "可直接替代")


class NewCandidateTest(unittest.TestCase):
    def test_selected_ids_are_excluded_from_new_candidates(self):
        specs = [
            {"uqer_indic_id": "U1", "industry_code": "801010", "candidate_type": "新增行业指标"},
            {"uqer_indic_id": "U2", "industry_code": "801030", "candidate_type": "新增行业指标"},
        ]
        metadata = {
            "U1": {"indicID": "U1", "indicName": "全国生猪价格", "frequency": "日"},
            "U2": {"indicID": "U2", "indicName": "PTA价格", "frequency": "周"},
        }

        rows = materialize_candidate_specs(specs, metadata, {"U2"})

        self.assertEqual([row["uqer_indic_id"] for row in rows], ["U1"])
        self.assertEqual(rows[0]["uqer_name"], "全国生猪价格")


if __name__ == "__main__":
    unittest.main()
