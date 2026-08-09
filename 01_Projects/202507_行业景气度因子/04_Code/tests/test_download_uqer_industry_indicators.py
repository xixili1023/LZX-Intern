from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "download_uqer_industry_indicators.py"
)
SPEC = importlib.util.spec_from_file_location("uqer_industry_downloader", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeDataAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def EcoInfoProGet(self, **kwargs):
        self.calls.append(("EcoInfoProGet", kwargs))
        return pd.DataFrame(
            [
                {
                    "indicID": "2010000007",
                    "indicName": "测试指标一",
                    "isList": 0,
                    "frequency": "月",
                    "unit": "万吨",
                    "dataApiName": "EcoDataIndAgriculturalGet",
                    "isUpdate": 1,
                },
                {
                    "indicID": "2010000008",
                    "indicName": "测试指标二",
                    "isList": 0,
                    "frequency": "月",
                    "unit": "%",
                    "dataApiName": "EcoDataIndAgriculturalGet",
                    "isUpdate": 1,
                },
            ]
        )

    def __getattr__(self, api_name):
        def caller(**kwargs):
            self.calls.append((api_name, kwargs))
            ids = kwargs["indicID"].split(",")
            return pd.DataFrame(
                [
                    {
                        "indicID": indic_id,
                        "publishDate": "20240201",
                        "periodDate": "20240131",
                        "dataValue": float(index + 1),
                        "updateTime": "20240202T000000",
                    }
                    for index, indic_id in enumerate(ids)
                ]
            )

        return caller


class DownloaderTest(unittest.TestCase):
    def write_catalog(self, root: Path) -> Path:
        path = root / "catalog.csv"
        pd.DataFrame(
            [
                {
                    "scope": "行业经济",
                    "category": "农林牧渔",
                    "api_name": "EcoDataIndAgriculturalGet",
                    "metadata_api_name": "getEcoDataIndAgricultural",
                    "sample_indic_id": "2010000007",
                    "enabled": "1",
                    "review_status": "provided",
                    "review_note": "test",
                },
                {
                    "scope": "行业经济",
                    "category": "错标行",
                    "api_name": "EcoDataWrongGet",
                    "metadata_api_name": "getEcoDataWrong",
                    "sample_indic_id": "999",
                    "enabled": "0",
                    "review_status": "suspected_mislabel",
                    "review_note": "test",
                },
            ]
        ).to_csv(path, index=False)
        return path

    def test_sample_mode_downloads_only_sample_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = FakeDataAPI()
            downloader = MODULE.UqerIndustryDownloader(
                catalog_path=self.write_catalog(root),
                output_root=root / "output",
                snapshot_id="sample-test",
                start_date="20240101",
                end_date="20241231",
                data_api=fake,
            )
            snapshot = downloader.run("sample")

            data_files = list((snapshot / "data").rglob("*.parquet"))
            self.assertEqual(len(data_files), 1)
            data = pd.read_parquet(data_files[0])
            self.assertEqual(data["indicID"].tolist(), ["2010000007"])
            self.assertNotIn("EcoDataWrongGet", [name for name, _ in fake.calls])

            manifest = json.loads((snapshot / "manifest.json").read_text())
            self.assertEqual(manifest["summary"]["failed_calls"], 0)
            self.assertEqual(manifest["summary"]["successful_calls"], 2)

    def test_full_mode_discovers_metadata_ids_and_batches_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = FakeDataAPI()
            downloader = MODULE.UqerIndustryDownloader(
                catalog_path=self.write_catalog(root),
                output_root=root / "output",
                snapshot_id="full-test",
                start_date="20240101",
                end_date="20241231",
                batch_size=1,
                allow_all_indicators=True,
                data_api=fake,
            )
            snapshot = downloader.run("full")

            data_files = sorted((snapshot / "data").rglob("*.parquet"))
            self.assertEqual(len(data_files), 2)
            downloaded_ids = [
                pd.read_parquet(path)["indicID"].iloc[0]
                for path in data_files
            ]
            self.assertEqual(downloaded_ids, ["2010000007", "2010000008"])
            metadata_call = next(
                kwargs
                for name, kwargs in fake.calls
                if name == "EcoInfoProGet"
            )
            self.assertEqual(
                metadata_call["dataApiName"], "getEcoDataIndAgricultural"
            )

    def test_full_mode_requires_explicit_unlock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloader = MODULE.UqerIndustryDownloader(
                catalog_path=self.write_catalog(root),
                output_root=root / "output",
                snapshot_id="locked-full-test",
                start_date="20240101",
                end_date="20241231",
                data_api=FakeDataAPI(),
            )
            with self.assertRaisesRegex(ValueError, "allow-all-indicators"):
                downloader.run("full")

    def test_selected_mode_downloads_only_enabled_selection_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selection = root / "selection.csv"
            pd.DataFrame(
                [
                    {
                        "uqer_indic_id": "2010000008",
                        "uqer_api_name": "EcoDataIndAgriculturalGet",
                        "download_enabled": "1",
                    },
                    {
                        "uqer_indic_id": "2010000007",
                        "uqer_api_name": "EcoDataIndAgriculturalGet",
                        "download_enabled": "0",
                    },
                ]
            ).to_csv(selection, index=False)
            fake = FakeDataAPI()
            downloader = MODULE.UqerIndustryDownloader(
                catalog_path=self.write_catalog(root),
                output_root=root / "output",
                snapshot_id="selected-test",
                start_date="20240101",
                end_date="20241231",
                selection_path=selection,
                data_api=fake,
            )
            snapshot = downloader.run("selected")

            data_file = next((snapshot / "data").rglob("*.parquet"))
            data = pd.read_parquet(data_file)
            self.assertEqual(data["indicID"].tolist(), ["2010000008"])


if __name__ == "__main__":
    unittest.main()
