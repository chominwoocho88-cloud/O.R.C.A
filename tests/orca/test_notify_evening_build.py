import unittest


class EveningTelegramBuildTests(unittest.TestCase):
    def test_evening_preserves_existing_sections(self):
        from orca.notify import _build_evening

        lines = _build_evening(
            {
                "tomorrow_setup": "코스피 개장 전 외국인 수급과 엔비디아 시간외 흐름 확인",
                "counterarguments": [
                    {"against": "엔비디아 실적 선반영"},
                    {"against": "외국인 순매도 지속"},
                ],
                "tail_risks": ["유가 급등 재개"],
            }
        )
        message = "\n".join(lines)

        self.assertIn("━━ 오늘 총정리 ━━", message)
        self.assertIn("🌙 <b>내일 준비</b>", message)
        self.assertIn("코스피 개장 전 외국인 수급", message)
        self.assertIn("⚔️ <b>주요 리스크</b>", message)
        self.assertIn("엔비디아 실적 선반영", message)
        self.assertIn("☠️ 유가 급등 재개", message)

    def test_evening_renders_operational_fallback_sections(self):
        from orca.notify import _build_evening

        lines = _build_evening(
            {
                "top_headlines": [
                    {"headline": "엔비디아 실적 발표 대기", "signal_tag": "CATALYST", "impact": "높음"},
                ],
                "outflows": [
                    {"zone": "KOSPI", "severity": "높음", "reason": "외국인 9거래일 순매도 지속"},
                ],
                "inflows": [
                    {"zone": "AI 반도체", "momentum": "강함", "reason": "데이터센터 백로그 확대"},
                ],
                "thesis_killers": [
                    {
                        "event": "코스피",
                        "timeframe": "5/21 종가",
                        "confirms_if": "7,400pt 이상 회복",
                        "invalidates_if": "7,000pt 이하 이탈",
                    },
                ],
                "hidden_signals": [
                    {
                        "signal": "VKOSPI 과열 해소",
                        "implication": "단기 반등 가능성은 있으나 구조적 이탈 지속",
                    },
                ],
            }
        )
        message = "\n".join(lines)

        self.assertIn("📰 <b>주요 헤드라인</b>", message)
        self.assertIn("엔비디아 실적 발표 대기", message)
        self.assertIn("▼ <b>자금 이탈</b>", message)
        self.assertIn("외국인 9거래일 순매도 지속", message)
        self.assertIn("▲ <b>자금 유입</b>", message)
        self.assertIn("데이터센터 백로그 확대", message)
        self.assertIn("⚠️ <b>Thesis Killer</b>", message)
        self.assertIn("7,000pt 이하 이탈", message)
        self.assertIn("🔍 <b>Hidden Signal</b>", message)
        self.assertIn("구조적 이탈 지속", message)

    def test_evening_empty_report_keeps_header_only(self):
        from orca.notify import _build_evening

        self.assertEqual(_build_evening({}), ["━━ 오늘 총정리 ━━", ""])

    def test_evening_fallback_stays_under_single_telegram_chunk(self):
        from orca.notify import _build_evening

        long = "매우 긴 설명 " * 80
        report = {
            "top_headlines": [
                {"headline": f"헤드라인 {idx} {long}", "signal_tag": "TAG", "impact": "높음"}
                for idx in range(6)
            ],
            "outflows": [
                {"zone": f"이탈 {idx} {long}", "severity": "높음", "reason": long}
                for idx in range(5)
            ],
            "inflows": [
                {"zone": f"유입 {idx} {long}", "momentum": "강함", "reason": long}
                for idx in range(5)
            ],
            "thesis_killers": [
                {
                    "event": f"트리거 {idx} {long}",
                    "timeframe": "단기",
                    "confirms_if": long,
                    "invalidates_if": long,
                }
                for idx in range(5)
            ],
            "hidden_signals": [
                {"signal": f"히든 {idx} {long}", "implication": long}
                for idx in range(5)
            ],
        }

        message = "\n".join(_build_evening(report))

        self.assertLess(len(message), 4000)
        self.assertIn("…", message)
        self.assertNotIn("헤드라인 5", message)


if __name__ == "__main__":
    unittest.main()
