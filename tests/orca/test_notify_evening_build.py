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

    def test_evening_renders_tomorrow_korea_forecast_sections(self):
        from orca.notify import _build_evening

        lines = _build_evening(
            {
                "tomorrow_korea_open": {
                    "direction": "갭업",
                    "expected_gap_pct": "+0.6~1.1%",
                    "kospi_open_range": "KOSPI 7,250~7,310 예상",
                    "sk_hynix": "나스닥 반도체 강세를 1.36x beta로 반영",
                    "samsung": "코스피 대형주 동조로 소폭 강세",
                    "confidence": "보통",
                },
                "tomorrow_korea_levels": {
                    "kospi_support": "7,180",
                    "kospi_resistance": "7,360",
                    "watch_level": "7,250 이탈 여부",
                    "breakdown_risk": "7,180 이탈 시 외국인 매도 재가속",
                },
                "us_to_korea_impact": {
                    "us_signal": "나스닥 +1.2%, 엔비디아 시간외 +4%",
                    "expected_korea_impact": "한국 반도체 갭업 압력",
                    "sk_hynix_beta_note": "나스닥 대비 1.36x beta 적용",
                    "samsung_note": "메모리 동조이나 베타는 낮게 반영",
                },
                "tomorrow_korea_catalysts": [
                    {
                        "event": "엔비디아 실적 반응",
                        "time_kst": "06:00 KST",
                        "why_it_matters": "한국 반도체 개장 방향 결정",
                        "directional_trigger": "AH +5% 이상이면 SK하이닉스 갭업 우위",
                    }
                ],
            }
        )
        message = "\n".join(lines)

        self.assertIn("🌅 <b>내일 한국 시장 예상</b>", message)
        self.assertIn("갭업 / +0.6~1.1% / KOSPI 7,250~7,310 예상 / 보통", message)
        self.assertIn("SK하이닉스: 나스닥 반도체 강세", message)
        self.assertIn("📊 <b>KOSPI 레벨</b>", message)
        self.assertIn("지지: 7,180", message)
        self.assertIn("🇺🇸→🇰🇷 <b>미국 영향</b>", message)
        self.assertIn("나스닥 대비 1.36x beta 적용", message)
        self.assertIn("⚡ <b>내일 catalyst</b>", message)
        self.assertIn("AH +5% 이상이면 SK하이닉스 갭업 우위", message)

    def test_evening_skips_empty_tomorrow_korea_forecast_fields(self):
        from orca.notify import _build_evening

        lines = _build_evening(
            {
                "tomorrow_korea_open": {
                    "direction": "",
                    "expected_gap_pct": "",
                    "kospi_open_range": "",
                    "sk_hynix": "",
                    "samsung": "",
                    "confidence": "",
                },
                "tomorrow_korea_levels": {},
                "us_to_korea_impact": {"us_signal": "", "expected_korea_impact": ""},
                "tomorrow_korea_catalysts": [{"event": "", "why_it_matters": ""}],
            }
        )

        self.assertEqual(lines, ["━━ 오늘 총정리 ━━", ""])

    def test_evening_renders_mixed_tomorrow_korea_forecast_shapes(self):
        from orca.notify import _build_evening

        lines = _build_evening(
            {
                "tomorrow_korea_open": "보합 출발 후 외국인 수급 확인",
                "us_to_korea_impact": "미국 장 보합이면 한국은 개별 반도체 수급 우선",
                "tomorrow_korea_catalysts": ["한국 수출 잠정치", "Fed 발언"],
            }
        )
        message = "\n".join(lines)

        self.assertIn("🌅 <b>내일 한국 시장 예상</b>", message)
        self.assertIn("보합 출발 후 외국인 수급 확인", message)
        self.assertIn("🇺🇸→🇰🇷 <b>미국 영향</b>", message)
        self.assertIn("⚡ <b>내일 catalyst</b>", message)
        self.assertIn("한국 수출 잠정치", message)

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
            "tomorrow_korea_open": {
                "direction": "갭업",
                "expected_gap_pct": long,
                "kospi_open_range": long,
                "sk_hynix": long,
                "samsung": long,
                "confidence": "보통",
            },
            "tomorrow_korea_levels": {
                "kospi_support": long,
                "kospi_resistance": long,
                "watch_level": long,
                "breakdown_risk": long,
            },
            "us_to_korea_impact": {
                "us_signal": long,
                "expected_korea_impact": long,
                "sk_hynix_beta_note": long,
                "samsung_note": long,
            },
            "tomorrow_korea_catalysts": [
                {
                    "event": f"촉매 {idx} {long}",
                    "time_kst": "06:00 KST",
                    "why_it_matters": long,
                    "directional_trigger": long,
                }
                for idx in range(5)
            ],
        }

        message = "\n".join(_build_evening(report))

        self.assertLess(len(message), 4000)
        self.assertIn("…", message)
        self.assertNotIn("헤드라인 5", message)


if __name__ == "__main__":
    unittest.main()
