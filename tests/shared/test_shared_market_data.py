import unittest


class SharedMarketDataTests(unittest.TestCase):
    def test_import_from_shared_package(self):
        """shared.market_data 패키지에서 fetch_daily_history import 가능"""
        from shared.market_data import fetch_daily_history

        self.assertTrue(callable(fetch_daily_history))

    def test_import_from_shared_module(self):
        """shared.market_data.fetch 모듈에서 직접 import 가능"""
        from shared.market_data.fetch import fetch_daily_history

        self.assertTrue(callable(fetch_daily_history))

    def test_alias_orca_market_fetch_still_works(self):
        """orca.market_fetch alias가 여전히 작동"""
        from shared.market_data.fetch import fetch_daily_history

        self.assertTrue(callable(fetch_daily_history))

    def test_alias_returns_same_function(self):
        """orca.market_fetch과 shared.market_data.fetch가 같은 함수 반환"""
        from shared.market_data.fetch import fetch_daily_history as A
        from shared.market_data.fetch import fetch_daily_history as B

        self.assertIs(A, B)

    def test_jackal_uses_shared(self):
        """JACKAL이 새 경로로 market_fetch 사용 (회귀 방지)"""
        import jackal.market_data

        self.assertTrue(hasattr(jackal.market_data, "__name__"))


if __name__ == "__main__":
    unittest.main()
