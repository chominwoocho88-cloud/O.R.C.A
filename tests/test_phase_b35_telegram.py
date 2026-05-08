import os
import unittest
from unittest.mock import patch


class PhaseB35TelegramTests(unittest.TestCase):
    def test_get_build_info_with_github_sha(self):
        """GITHUB_SHA 환경변수 있으면 short hash 반환"""
        with patch.dict(os.environ, {"GITHUB_SHA": "a98e759833aa570d55a01b8c0915f11bf4aa3477"}):
            from shared.build_info import get_build_info

            self.assertEqual(get_build_info(), "a98e759")

    def test_get_build_info_local(self):
        """GITHUB_SHA 없으면 'local' 반환"""
        with patch.dict(os.environ, {}, clear=True):
            from shared.build_info import get_build_info

            self.assertEqual(get_build_info(), "local")

    def test_build_info_in_telegram_message(self):
        """텔레그램 메시지에 build 표시 포함"""
        from orca.notify import send_report

        report = {
            "mode": "MORNING",
            "market_regime": "위험선호",
            "confidence_overall": "높음",
            "analysis_date": "2026-05-08",
            "analysis_time": "09:00 KST",
            "one_line_summary": "테스트 요약",
        }
        with patch.dict(os.environ, {"GITHUB_SHA": "a98e759833aa570d55a01b8c0915f11bf4aa3477"}):
            with patch("orca.notify.get_active_lessons", return_value=[]):
                with patch("orca.notify.send_message") as mock_send:
                    send_report(report, 1)
                    message = mock_send.call_args.args[0]

        self.assertIn("build: a98e759", message)

    def test_long_trigger_not_truncated(self):
        """트리거 조건은 짤리지 않음"""
        from orca.notify import _build_morning

        long_trigger = "코스피 7,400pt 이상 유지 + 외국인 순매도 3조 이하 → 단기 천장 아닌 눌림목 확인"
        report = {
            "thesis_killers": [
                {
                    "timeframe": "단기",
                    "event": "트리거 테스트",
                    "confirms_if": long_trigger,
                    "invalidates_if": long_trigger + " 실패",
                }
            ]
        }

        message = "\n".join(_build_morning(report))

        self.assertIn("✓ " + long_trigger, message)
        self.assertIn("✗ " + long_trigger + " 실패", message)

    def test_sector_reason_limit_keeps_reported_phrase(self):
        """섹터 설명의 기존 70자 절단으로 잘리던 구문을 보존"""
        from orca.notify import _build_morning

        reason = (
            "AI 수익화 대비 과도한 투자 부담과 S&P500 밸류에이션 압력이 동시에 커졌지만 "
            "단기 변동성은 아직 관리 가능한 수준"
        )
        report = {"outflows": [{"zone": "AI", "severity": "보통", "reason": reason}]}

        message = "\n".join(_build_morning(report))

        self.assertIn(reason, message)
        self.assertIn("S&P500", message)

    def test_korean_word_boundary(self):
        """한글 단어 경계에서 부드럽게 줄임"""
        from orca.notify import _report_line_text

        text = "AI 수익화 대비 과도한 투자 부담"
        shortened = _report_line_text(text, limit=13)

        self.assertEqual(shortened, "AI 수익화 대비…")


if __name__ == "__main__":
    unittest.main()
