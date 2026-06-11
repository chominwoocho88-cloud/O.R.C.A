"""KIS 자격증명 단일 소스 — ATLAS JSON 폴백 (2026-06-11 env 정리).

KIS_CMW_*가 없으면 공용 .env의 KIS_PROD_CREDENTIALS/KIS_PAPER_CREDENTIAL(JSON)을
읽고, 모드는 KIS_ENV를 따른다. KIS_CMW_*는 별도 앱키 분리용 오버라이드.
"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from shared.broker.kis import (
    PAPER_BASE_URL,
    PROD_BASE_URL,
    _get_account_number,
    _get_app_key,
    _get_app_secret,
    get_kis_base_url,
)

PAPER_JSON = json.dumps(
    {"label": "paper", "app_key": "atlas-paper-key", "app_secret": "atlas-paper-secret",
     "account_cano": "50186519", "account_prdt": "01"}
)
PROD_JSON = json.dumps(
    [{"label": "main", "app_key": "atlas-prod-key", "app_secret": "atlas-prod-secret",
      "account_cano": "12345678", "account_prdt": "01"}]
)


class KisSharedCredentialTests(unittest.TestCase):
    def test_empty_strings_are_treated_as_unset(self):
        # docker-compose의 ${VAR:-}는 ""를 주입 — prod 오판 방지
        env = {"KIS_IS_PAPER": "", "KIS_ENV": ""}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(get_kis_base_url(), PAPER_BASE_URL)
        env = {"KIS_IS_PAPER": "", "KIS_ENV": "prod"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(get_kis_base_url(), PROD_BASE_URL)

    def test_kis_env_controls_mode(self):
        with patch.dict(os.environ, {"KIS_ENV": "prod"}, clear=True):
            self.assertEqual(get_kis_base_url(), PROD_BASE_URL)
        with patch.dict(os.environ, {"KIS_ENV": "paper"}, clear=True):
            self.assertEqual(get_kis_base_url(), PAPER_BASE_URL)
        with patch.dict(os.environ, {"KIS_ENV": "prod", "KIS_IS_PAPER": "true"}, clear=True):
            self.assertEqual(get_kis_base_url(), PAPER_BASE_URL)  # 레거시 오버라이드

    def test_atlas_json_fallback(self):
        env = {"KIS_ENV": "paper", "KIS_PAPER_CREDENTIAL": PAPER_JSON}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(_get_app_key(), "atlas-paper-key")
            self.assertEqual(_get_app_secret(), "atlas-paper-secret")
            self.assertEqual(_get_account_number(), "50186519-01")
        env = {"KIS_ENV": "prod", "KIS_PROD_CREDENTIALS": PROD_JSON}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(_get_app_key(), "atlas-prod-key")
            self.assertEqual(_get_account_number(), "12345678-01")

    def test_kis_cmw_override_wins(self):
        env = {
            "KIS_ENV": "paper",
            "KIS_PAPER_CREDENTIAL": PAPER_JSON,
            "KIS_CMW_APP_KEY_PAPER": "dedicated-app-key",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(_get_app_key(), "dedicated-app-key")
            self.assertEqual(_get_app_secret(), "atlas-paper-secret")

    def test_malformed_or_missing_degrades_to_empty(self):
        with patch.dict(os.environ, {"KIS_ENV": "paper", "KIS_PAPER_CREDENTIAL": "{bad"}, clear=True):
            self.assertEqual(_get_app_key(), "")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_get_account_number(), "")


if __name__ == "__main__":
    unittest.main()
