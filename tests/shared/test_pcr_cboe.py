"""put/call 소스 교체 검증 — CBOE 1차, yfinance 폴백 (API 로드맵 A3).

배경(2026-06 진단): yfinance 옵션 경로가 "options provider down"으로 자주
실패해 PCR이 N/A로 빠짐. CBOE 공식 무료 API(delayed_quotes 옵션 체인)를
1차 소스로 승격하고, 실패 시에만 기존 yfinance 경로로 폴백한다.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from shared.market_data import fetch as fetch_module
from shared.market_data.fetch import _cboe_put_call_volume, fetch_put_call_ratio_summary


def _cboe_payload(call_volume: float, put_volume: float) -> dict:
    return {
        "data": {
            "options": [
                {"option": "SPY260612C00500000", "volume": call_volume},
                {"option": "SPY260612P00500000", "volume": put_volume},
                {"option": "잘못된심볼", "volume": 999.0},  # 무시돼야 함
            ]
        }
    }


# create=True: 일부 테스트(test_notify_and_agents 등)가 sys.modules의 httpx를
# get 없는 스텁으로 교체한 채 남겨둠 — 전체 스위트 순서에서도 patch가 성립해야 한다.


def _http_response(status_code: int = 200, payload: dict | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    return response


class CboePutCallVolumeTests(unittest.TestCase):
    def test_computes_volume_pcr_from_chain(self):
        with patch("httpx.get", create=True, return_value=_http_response(200, _cboe_payload(200.0, 150.0))):
            self.assertEqual(_cboe_put_call_volume("SPY"), 0.75)

    def test_http_error_returns_none(self):
        with patch("httpx.get", create=True, return_value=_http_response(403)):
            self.assertIsNone(_cboe_put_call_volume("SPY"))

    def test_zero_call_volume_returns_none(self):
        with patch("httpx.get", create=True, return_value=_http_response(200, _cboe_payload(0.0, 10.0))):
            self.assertIsNone(_cboe_put_call_volume("SPY"))

    def test_network_exception_returns_none(self):
        with patch("httpx.get", create=True, side_effect=RuntimeError("proxy down")):
            self.assertIsNone(_cboe_put_call_volume("SPY"))


class SummarySourceOrderTests(unittest.TestCase):
    def test_cboe_primary_skips_yfinance(self):
        with patch.object(fetch_module, "_cboe_put_call_volume", side_effect=[0.8, 1.2]) as cboe, \
             patch.object(fetch_module, "_option_expiries") as expiries:
            result = fetch_put_call_ratio_summary(sleep_seconds=0)

        self.assertEqual(cboe.call_count, 2)
        expiries.assert_not_called()  # CBOE 성공 시 yfinance 경로 진입 금지
        self.assertEqual(result["pcr_spy"], 0.8)
        self.assertEqual(result["pcr_qqq"], 1.2)
        self.assertEqual(result["pcr_avg"], 1.0)
        self.assertNotEqual(result["pcr_signal"], "N/A")

    def test_falls_back_to_yfinance_when_cboe_fails(self):
        with patch.object(fetch_module, "_cboe_put_call_volume", return_value=None), \
             patch.object(fetch_module, "_option_expiries", return_value=["2026-06-19"]), \
             patch.object(
                 fetch_module, "fetch_put_call_ratio",
                 return_value={"call_volume": 100, "pcr_volume": 0.9},
             ):
            result = fetch_put_call_ratio_summary(tickers=("SPY",), sleep_seconds=0)

        self.assertEqual(result["pcr_spy"], 0.9)
        self.assertEqual(result["pcr_avg"], 0.9)

    def test_all_sources_down_keeps_na_schema(self):
        with patch.object(fetch_module, "_cboe_put_call_volume", return_value=None), \
             patch.object(fetch_module, "_option_expiries", side_effect=RuntimeError("down")):
            result = fetch_put_call_ratio_summary(tickers=("SPY",), sleep_seconds=0)

        self.assertEqual(
            result,
            {"pcr_spy": None, "pcr_qqq": None, "pcr_avg": None, "pcr_signal": "N/A"},
        )


if __name__ == "__main__":
    unittest.main()
