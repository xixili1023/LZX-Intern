import unittest

import pandas as pd

from scripts.uqer_supplement import (
    DEFAULT_CLIENT_DIR,
    build_query_plan,
    classify_query_error,
    execute_query_plan,
    normalize_wind_ticker,
)


class _UnavailableGatewayAPI:
    def __getattr__(self, _name):
        def fail(**_kwargs):
            raise RuntimeError("无法连接网关 http://[redacted]:8713")

        return fail


class _EmptyAPI:
    def __getattr__(self, _name):
        def empty(**_kwargs):
            return pd.DataFrame()

        return empty


class UqerSupplementTests(unittest.TestCase):
    def test_default_client_is_next_to_the_supplement_script(self):
        self.assertEqual(DEFAULT_CLIENT_DIR.name, "scripts")
        self.assertTrue((DEFAULT_CLIENT_DIR / "client.py").is_file())

    def test_normalize_wind_ticker_removes_only_wind_suffix(self):
        self.assertEqual(normalize_wind_ticker("CI011800.WI"), "CI011800")
        self.assertEqual(normalize_wind_ticker("GALLW"), "GALLW")

    def test_classify_gateway_privilege_and_quota_errors(self):
        self.assertEqual(classify_query_error(Exception("无法连接网关")), "网关不可达")
        self.assertEqual(
            classify_query_error(Exception("无IdxConsGet接口使用权限")),
            "上游无接口权限",
        )
        self.assertEqual(
            classify_query_error(Exception("通联账号今日额度已用尽")),
            "配额用尽",
        )

    def test_plan_contains_four_indices_and_four_required_endpoints(self):
        plan = build_query_plan()
        self.assertEqual(
            {item.wind_ticker for item in plan},
            {"CI011800.WI", "CICSF040.WI", "CI011001.WI", "GALLW.WI"},
        )
        self.assertTrue(
            {"IdxGet", "MktIdxdGet", "IdxConsGet", "IdxCloseWeightGet"}.issubset(
                {item.endpoint for item in plan}
            )
        )

    def test_gateway_failure_stops_without_claiming_empty_data(self):
        status, outputs = execute_query_plan(_UnavailableGatewayAPI(), build_query_plan())
        self.assertEqual(status.iloc[0]["状态"], "网关不可达")
        self.assertTrue(
            (status.iloc[1:]["状态"] == "未执行（前置网关不可达）").all()
        )
        self.assertNotIn("空结果", set(status["状态"]))
        self.assertEqual(outputs, {})

    def test_authenticated_empty_frame_is_an_empty_result(self):
        status, outputs = execute_query_plan(_EmptyAPI(), build_query_plan()[:1])
        self.assertEqual(status.iloc[0]["状态"], "空结果")
        self.assertEqual(status.iloc[0]["返回行数"], 0)
        self.assertEqual(outputs, {})


if __name__ == "__main__":
    unittest.main()
