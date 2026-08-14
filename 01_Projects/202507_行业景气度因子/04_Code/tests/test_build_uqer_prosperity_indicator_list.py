from __future__ import annotations

import importlib.util
import csv
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "build_uqer_prosperity_indicator_list.py"
)
SPEC = importlib.util.spec_from_file_location("uqer_prosperity_list", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class MetadataEligibilityTest(unittest.TestCase):
    def test_duplicate_indicator_ids_keep_one_metadata_record(self):
        rows = [
            {"indicID": 1, "indicName": "旧名称", "endDate": "2026-06-30"},
            {"indicID": "1", "indicName": "现名称", "endDate": "2026-07-31"},
        ]

        deduplicated = MODULE.deduplicate_metadata(rows)

        self.assertEqual(list(deduplicated), ["1"])
        self.assertEqual(deduplicated["1"]["indicName"], "现名称")

    def test_approved_indicator_ids_are_removed_from_candidate_rows(self):
        rows = [{"indicID": "1"}, {"indicID": "2"}]

        remaining = MODULE.exclude_approved_ids(rows, {"1"})

        self.assertEqual(remaining, [{"indicID": "2"}])

    def test_annual_series_is_not_eligible_for_core_prosperity_list(self):
        row = self.valid_row(frequency="年", endDate="2025-12-31")

        self.assertFalse(MODULE.is_metadata_eligible(row))

    def test_series_starting_after_research_sample_is_not_eligible(self):
        row = self.valid_row(beginDate="2019-01-01")

        self.assertFalse(MODULE.is_metadata_eligible(row))

    def test_stale_monthly_series_is_not_eligible(self):
        row = self.valid_row(endDate="2025-12-31")

        self.assertFalse(MODULE.is_metadata_eligible(row))

    def test_current_monthly_series_with_full_history_is_eligible(self):
        row = self.valid_row()

        self.assertTrue(MODULE.is_metadata_eligible(row))

    @staticmethod
    def valid_row(**overrides):
        row = {
            "frequency": "月",
            "beginDate": "2010-01-31",
            "endDate": "2026-06-30",
            "isUpdate": 1,
        }
        row.update(overrides)
        return row


class IndustryRelevanceTest(unittest.TestCase):
    STEEL_PROFILE = {
        "core_terms": ["钢材", "螺纹钢", "热轧", "不锈钢"],
        "support_terms": ["库存", "产量", "价格", "出口"],
        "exclude_terms": ["公司"],
        "preferred_apis": ["getEcoDataIndSteel"],
        "global_scope_allowed": False,
    }
    BANK_PROFILE = {
        "core_terms": ["贷款", "存款", "净息差", "不良贷款"],
        "support_terms": ["余额", "同比", "利率"],
        "exclude_terms": ["公司"],
        "preferred_apis": ["getEcoDataIndFinancialservices"],
        "global_scope_allowed": False,
    }

    def test_steel_inventory_scores_for_steel_but_not_bank(self):
        row = {
            "indicID": "1",
            "indicName": "全国钢材社会库存",
            "region": "全国",
            "frequency": "周",
            "dataApiName": "getEcoDataIndSteel",
        }

        steel_score = MODULE.score_candidate("801040", row, self.STEEL_PROFILE)
        bank_score = MODULE.score_candidate("801780", row, self.BANK_PROFILE)

        self.assertGreater(steel_score, bank_score)

    def test_broad_industry_series_outranks_overly_narrow_hs_product(self):
        broad = {
            "indicID": "1", "indicName": "产量:钢材:当月同比", "region": "全国",
            "frequency": "月", "dataApiName": "getEcoDataIndSteel",
        }
        narrow = {
            "indicID": "2",
            "indicName": "出口数量:其他冷轧不锈钢板材,1mm<厚<3mm(72193390):当月同比",
            "region": "全国", "frequency": "月", "dataApiName": "getEcoDataIndSteel",
        }

        self.assertGreater(
            MODULE.score_candidate("801040", broad, self.STEEL_PROFILE),
            MODULE.score_candidate("801040", narrow, self.STEEL_PROFILE),
        )

    def test_local_city_series_is_disallowed_for_national_industry_profile(self):
        row = {"indicName": "上海某商场销售额", "region": "上海"}

        self.assertTrue(MODULE.has_disallowed_scope(row, self.BANK_PROFILE))

    def test_named_city_price_series_is_disallowed_even_when_region_is_blank(self):
        row = {"indicName": "价格:三级螺纹钢(25mm):成都", "region": ""}

        self.assertTrue(MODULE.has_disallowed_scope(row, self.STEEL_PROFILE))

    def test_industry_benchmark_location_can_be_explicitly_allowed(self):
        row = {"indicName": "秦皇岛动力煤价格", "region": "秦皇岛"}
        coal_profile = dict(self.STEEL_PROFILE, allowed_local_markers=["秦皇岛"])

        self.assertTrue(MODULE.has_disallowed_scope(row, self.STEEL_PROFILE))
        self.assertFalse(MODULE.has_disallowed_scope(row, coal_profile))

    def test_global_series_is_allowed_only_when_profile_explicitly_permits_it(self):
        row = {"indicName": "全球原油价格", "region": "全球", "country": "全球"}
        oil_profile = dict(self.STEEL_PROFILE, global_scope_allowed=True)

        self.assertFalse(MODULE.has_disallowed_scope(row, oil_profile))
        self.assertTrue(MODULE.has_disallowed_scope(row, self.STEEL_PROFILE))

    def test_foreign_country_series_is_rejected_without_explicit_country_allowance(self):
        row = {"indicName": "日本:产量:印刷电路板", "region": "日本", "country": "日本"}
        global_profile = dict(self.STEEL_PROFILE, global_scope_allowed=True)

        self.assertTrue(MODULE.has_disallowed_scope(row, global_profile))

    def test_company_announcement_series_is_not_an_industry_candidate(self):
        row = {
            "indicName": "士兰微:库存量:集成电路芯片",
            "infoSource": "上市公司公告",
            "region": "全国",
        }

        self.assertTrue(MODULE.is_company_specific(row))

    def test_value_yoy_and_mom_variants_share_one_indicator_family(self):
        value = "农产品集贸市场价格:仔猪(普通):当月值"
        yoy = "农产品集贸市场价格:仔猪(普通):当月同比"
        mom = "农产品集贸市场价格:仔猪(普通):当月环比"

        self.assertEqual(MODULE.indicator_family(value), MODULE.indicator_family(yoy))
        self.assertEqual(MODULE.indicator_family(value), MODULE.indicator_family(mom))

    def test_price_change_and_change_rate_share_the_price_level_family(self):
        level = "市场价:农产品:玉米(黄玉米二等)"
        change = "市场价:农产品:玉米(黄玉米二等):涨跌"
        change_rate = "市场价:农产品:玉米(黄玉米二等):涨跌幅"

        self.assertEqual(MODULE.indicator_family(level), MODULE.indicator_family(change))
        self.assertEqual(MODULE.indicator_family(level), MODULE.indicator_family(change_rate))

    def test_futures_open_high_low_close_share_one_contract_family(self):
        close = "收盘价:大商所:玉米期货价格指数"
        low = "最低价:大商所:玉米期货价格指数"
        high = "最高价:大商所:玉米期货价格指数"

        self.assertEqual(MODULE.indicator_family(close), MODULE.indicator_family(low))
        self.assertEqual(MODULE.indicator_family(close), MODULE.indicator_family(high))

    def test_fixed_base_and_mom_price_indices_share_one_family(self):
        fixed = "全国白酒定基价格指数:名酒"
        mom = "全国白酒环比价格指数:名酒"

        self.assertEqual(MODULE.indicator_family(fixed), MODULE.indicator_family(mom))

    def test_ascii_core_term_does_not_match_a_longer_product_token(self):
        profile = {
            "core_terms": ["PCB"], "support_terms": ["价格"], "exclude_terms": [],
            "preferred_apis": [], "global_scope_allowed": True,
        }
        row = {"indicName": "USB3.0(PCBA) 128GB:价格", "region": "全国", "frequency": "日"}

        self.assertEqual(MODULE.score_candidate("801080", row, profile), float("-inf"))

    def test_memo_text_cannot_create_industry_relevance_absent_from_indicator_name(self):
        profile = {
            "core_terms": ["玻璃"], "support_terms": ["产量"], "exclude_terms": [],
            "preferred_apis": [], "global_scope_allowed": False,
        }
        row = {
            "indicName": "产量:汽车:当月值", "nameEN": "Output: Automobile",
            "memoCN": "下游使用汽车玻璃", "region": "全国", "frequency": "月",
        }

        self.assertEqual(MODULE.score_candidate("801710", row, profile), float("-inf"))

    def test_minimum_and_maximum_quotes_share_one_price_family(self):
        low = "维生素:VE:50%:25kg:进口:最低价"
        high = "维生素:VE:50%:25kg:进口:最高价"

        self.assertEqual(MODULE.indicator_family(low), MODULE.indicator_family(high))

    def test_selection_keeps_only_one_statistical_variant_per_family(self):
        base = {
            "region": "全国", "frequency": "月", "dataApiName": "getEcoDataIndSteel",
        }
        rows = [
            dict(base, indicID="1", indicName="钢材社会库存:当月值"),
            dict(base, indicID="2", indicName="钢材社会库存:当月同比"),
            dict(base, indicID="3", indicName="螺纹钢价格:当月值"),
        ]

        selected = MODULE.select_industry_candidates(
            "801040", rows, self.STEEL_PROFILE, limit=30
        )

        self.assertEqual(len(selected), 2)

    def test_selection_caps_rows_from_one_product_term(self):
        base = {"region": "全国", "frequency": "月", "dataApiName": "getEcoDataIndSteel"}
        rows = [
            dict(base, indicID="1", indicName="螺纹钢价格"),
            dict(base, indicID="2", indicName="螺纹钢库存"),
            dict(base, indicID="3", indicName="螺纹钢出口数量"),
            dict(base, indicID="4", indicName="热轧钢材价格"),
        ]
        profile = dict(self.STEEL_PROFILE, max_per_core_term=2)

        selected = MODULE.select_industry_candidates("801040", rows, profile, limit=30)

        self.assertEqual(len(selected), 3)
        self.assertIn("4", {row["indicID"] for row in selected})
        self.assertEqual(sum("螺纹钢" in row["indicName"] for row in selected), 2)

    def test_same_indicator_id_cannot_repeat_within_one_industry(self):
        row = {
            "indicID": "1",
            "indicName": "全国钢材社会库存",
            "region": "全国",
            "frequency": "周",
            "dataApiName": "getEcoDataIndSteel",
        }

        selected = MODULE.select_industry_candidates(
            "801040", [row, dict(row)], self.STEEL_PROFILE, limit=30
        )

        self.assertEqual(len(selected), 1)


class ScreeningInputsTest(unittest.TestCase):
    EXPECTED_INDUSTRIES = {
        "801010", "801030", "801040", "801050", "801080", "801110", "801120",
        "801130", "801140", "801150", "801160", "801170", "801180", "801200",
        "801210", "801710", "801720", "801730", "801740", "801750", "801760",
        "801770", "801780", "801790", "801880", "801890", "801950", "801960",
    }

    def test_metadata_loader_reads_parquet_and_deduplicates_across_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "snapshot=one" / "metadata"
            second = root / "snapshot=two" / "metadata"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            pq.write_table(
                pa.Table.from_pylist(
                    [{"indicID": 1, "indicName": "旧名称", "endDate": "2026-06-30"}]
                ),
                first / "one.parquet",
            )
            pq.write_table(
                pa.Table.from_pylist(
                    [{"indicID": 1, "indicName": "现名称", "endDate": "2026-07-31"}]
                ),
                second / "two.parquet",
            )

            metadata = MODULE.load_uqer_metadata(root)

        self.assertEqual(metadata["1"]["indicName"], "现名称")

    def test_profile_file_defines_all_28_industries_and_required_keys(self):
        profile_path = SCRIPT.with_name("uqer_prosperity_industry_profiles.json")

        profiles = MODULE.load_profiles(profile_path)

        self.assertEqual(set(profiles), self.EXPECTED_INDUSTRIES)
        required = {
            "industry_name", "core_terms", "support_terms", "exclude_terms",
            "preferred_apis", "global_scope_allowed",
        }
        for profile in profiles.values():
            self.assertTrue(required.issubset(profile))
            self.assertTrue(profile["core_terms"])

    def test_build_shortlists_excludes_ineligible_and_approved_rows(self):
        valid = {
            "indicID": "1", "indicName": "全国钢材社会库存", "frequency": "周",
            "beginDate": "2010-01-01", "endDate": "2026-08-01", "isUpdate": 1,
            "region": "全国", "dataApiName": "getEcoDataIndSteel",
        }
        approved = dict(valid, indicID="2", indicName="全国钢材产量")
        stale = dict(valid, indicID="3", indicName="全国钢材价格", endDate="2024-01-01")
        profiles = {"801040": dict(IndustryRelevanceTest.STEEL_PROFILE, industry_name="钢铁")}

        shortlists = MODULE.build_shortlists(
            {row["indicID"]: row for row in (valid, approved, stale)},
            profiles,
            approved_ids={"2"},
            limit=80,
        )

        self.assertEqual(len(shortlists), 1)
        self.assertEqual(shortlists[0]["industry_code"], "801040")
        self.assertEqual(shortlists[0]["industry_name"], "钢铁")
        self.assertEqual(shortlists[0]["indicID"], "1")

    def test_approved_id_reader_uses_uqer_indicator_column(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "approved.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["uqer_indic_id"])
                writer.writeheader()
                writer.writerow({"uqer_indic_id": "100"})

            approved_ids = MODULE.load_approved_ids(path)

        self.assertEqual(approved_ids, {"100"})

    def test_compact_candidate_uses_only_auditable_metadata_fields(self):
        row = {
            "industry_code": "801040", "industry_name": "钢铁", "indicID": "1",
            "indicName": "全国钢材社会库存", "nameEN": "Steel Inventory",
            "frequency": "周", "unit": "万吨", "statType": "当期值",
            "region": "全国", "country": "中国", "infoSource": "兰格钢铁",
            "dataApiName": "getEcoDataIndSteel", "beginDate": "2006-01-01",
            "endDate": "2026-08-01", "isUpdate": 1, "selection_score": 151.0,
            "memoCN": "不应进入简表", "_score": 999,
        }

        compact = MODULE.compact_candidate(row)

        self.assertEqual(compact["uqer_indic_id"], "1")
        self.assertEqual(compact["uqer_name"], "全国钢材社会库存")
        self.assertNotIn("memoCN", compact)
        self.assertNotIn("_score", compact)

    def test_csv_writer_preserves_chinese_headers_and_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "list.csv"
            MODULE.write_csv(path, [{"行业": "钢铁", "指标": "钢材库存"}], ["行业", "指标"])
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows, [{"行业": "钢铁", "指标": "钢材库存"}])

    def test_finalize_candidates_outputs_exactly_30_rows_per_industry(self):
        profiles = {code: {"industry_name": code} for code in ("A", "B")}
        rows = [
            {
                "industry_code": code, "industry_name": code,
                "uqer_indic_id": f"{code}{number}", "uqer_name": f"指标{number}",
            }
            for code in profiles
            for number in range(35)
        ]

        final = MODULE.finalize_candidates(rows, profiles, per_industry=30)

        self.assertEqual(len(final), 60)
        self.assertEqual(Counter(row["industry_code"] for row in final), {"A": 30, "B": 30})

    def test_finalize_candidates_rejects_an_industry_with_fewer_than_30_rows(self):
        profiles = {"A": {"industry_name": "A"}}
        rows = [
            {"industry_code": "A", "uqer_indic_id": str(number), "uqer_name": str(number)}
            for number in range(29)
        ]

        with self.assertRaisesRegex(ValueError, "A.*29"):
            MODULE.finalize_candidates(rows, profiles, per_industry=30)


if __name__ == "__main__":
    unittest.main()
