import importlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd


builder = importlib.import_module("scripts.build_stock_name_cache")


class FakeFDR:
    def __init__(self, *, fail_markets=None):
        self.fail_markets = set(fail_markets or [])

    def StockListing(self, market):
        if market in self.fail_markets:
            raise RuntimeError(f"{market} down")
        if market == "KOSPI":
            return pd.DataFrame(
                [
                    {"Code": "005930", "Name": "Samsung Electronics"},
                    {"Code": "000660", "Name": "SK Hynix"},
                ]
            )
        if market == "KOSDAQ":
            return pd.DataFrame(
                [
                    {"Code": "086520", "Name": "EcoPro"},
                    {"Code": "247540", "Name": "EcoPro BM"},
                ]
            )
        return pd.DataFrame()


class TestBulkCacheBuild(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.cache_path = self.tmpdir / "stock_name_cache.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _read_cache(self):
        return json.loads(self.cache_path.read_text(encoding="utf-8"))

    def test_build_merges_with_existing(self):
        self.cache_path.write_text(
            json.dumps({"068270.KS": "Celltrion"}, ensure_ascii=False),
            encoding="utf-8",
        )

        stats = builder.build_cache(fdr_module=FakeFDR(), cache_path=self.cache_path)

        cache = self._read_cache()
        self.assertEqual(cache["068270.KS"], "Celltrion")
        self.assertEqual(cache["005930.KS"], "Samsung Electronics")
        self.assertEqual(cache["086520.KQ"], "EcoPro")
        self.assertEqual(stats["kospi_added"], 2)
        self.assertEqual(stats["kosdaq_added"], 2)

    def test_build_refresh_overwrites(self):
        self.cache_path.write_text(
            json.dumps({"999999.KS": "Old Name"}, ensure_ascii=False),
            encoding="utf-8",
        )

        builder.build_cache(refresh=True, fdr_module=FakeFDR(), cache_path=self.cache_path)

        cache = self._read_cache()
        self.assertNotIn("999999.KS", cache)
        self.assertEqual(cache["005930.KS"], "Samsung Electronics")
        self.assertEqual(cache["247540.KQ"], "EcoPro BM")

    def test_build_handles_fdr_failure(self):
        self.cache_path.write_text(
            json.dumps({"068270.KS": "Celltrion"}, ensure_ascii=False),
            encoding="utf-8",
        )

        stats = builder.build_cache(
            fdr_module=FakeFDR(fail_markets={"KOSPI", "KOSDAQ"}),
            cache_path=self.cache_path,
        )

        cache = self._read_cache()
        self.assertEqual(cache, {"068270.KS": "Celltrion"})
        self.assertEqual(len(stats["errors"]), 2)

    def test_build_generates_meta_file(self):
        builder.build_cache(fdr_module=FakeFDR(), cache_path=self.cache_path)

        meta_path = self.cache_path.with_suffix(".meta.json")
        self.assertTrue(meta_path.exists())
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(meta["total_cached"], 4)
        self.assertIn("generated_at", meta)

    def test_build_kospi_kosdaq_suffix(self):
        builder.build_cache(fdr_module=FakeFDR(), cache_path=self.cache_path)

        cache = self._read_cache()
        self.assertIn("005930.KS", cache)
        self.assertIn("000660.KS", cache)
        self.assertIn("086520.KQ", cache)
        self.assertIn("247540.KQ", cache)


if __name__ == "__main__":
    unittest.main()
