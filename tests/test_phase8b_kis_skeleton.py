import os
import time
import unittest
from unittest.mock import MagicMock, patch

from shared.broker.kis import (
    PAPER_BASE_URL,
    PROD_BASE_URL,
    KisAuthError,
    KisClient,
    KisToken,
    get_kis_base_url,
)


class Phase8bKisSkeletonTests(unittest.TestCase):
    def test_paper_mode_default(self):
        """KIS_IS_PAPER unset defaults to paper trading."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_kis_base_url(), PAPER_BASE_URL)

    def test_paper_mode_true(self):
        """KIS_IS_PAPER=true uses paper trading."""
        with patch.dict(os.environ, {"KIS_IS_PAPER": "true"}):
            self.assertEqual(get_kis_base_url(), PAPER_BASE_URL)

    def test_prod_mode(self):
        """KIS_IS_PAPER=false uses production."""
        with patch.dict(os.environ, {"KIS_IS_PAPER": "false"}):
            self.assertEqual(get_kis_base_url(), PROD_BASE_URL)

    def test_token_valid(self):
        """Token expiring after the refresh margin is valid."""
        token = KisToken(access_token="test", expires_at=time.time() + 360)
        self.assertTrue(token.is_valid())

    def test_token_invalid_close_to_expire(self):
        """Token expiring inside the refresh margin is invalid."""
        token = KisToken(access_token="test", expires_at=time.time() + 60)
        self.assertFalse(token.is_valid())

    def test_token_invalid_empty(self):
        """Empty access_token is invalid."""
        token = KisToken(access_token="", expires_at=time.time() + 86400)
        self.assertFalse(token.is_valid())

    def test_client_not_configured(self):
        """Missing env variables make the client unconfigured."""
        with patch.dict(os.environ, {}, clear=True):
            client = KisClient()
            self.assertFalse(client.is_configured())

    def test_client_configured_paper(self):
        """Paper env variables configure the client."""
        with patch.dict(
            os.environ,
            {
                "KIS_IS_PAPER": "true",
                "KIS_CMW_APP_KEY_PAPER": "test_key",
                "KIS_CMW_APP_SECRET_PAPER": "test_secret",
                "KIS_CMW_ACCOUNT_NUMBER_PAPER": "12345",
            },
        ):
            client = KisClient()
            self.assertTrue(client.is_configured())

    @patch("shared.broker.kis.httpx.post")
    def test_get_token_success(self, mock_post):
        """get_token requests and stores a token."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "test_token_12345",
            "expires_in": 86400,
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        with patch.dict(
            os.environ,
            {
                "KIS_IS_PAPER": "true",
                "KIS_CMW_APP_KEY_PAPER": "test_key",
                "KIS_CMW_APP_SECRET_PAPER": "test_secret",
                "KIS_CMW_ACCOUNT_NUMBER_PAPER": "12345",
            },
        ):
            client = KisClient()
            token = client.get_token()
            self.assertEqual(token, "test_token_12345")
            mock_post.assert_called_once()

    @patch("shared.broker.kis.httpx.post")
    def test_get_token_no_config(self, mock_post):
        """Missing env variables raise without making HTTP calls."""
        with patch.dict(os.environ, {}, clear=True):
            client = KisClient()
            with self.assertRaises(KisAuthError):
                client.get_token()
            mock_post.assert_not_called()

    @patch("shared.broker.kis.httpx.post")
    def test_get_token_caches(self, mock_post):
        """A valid cached token avoids a second HTTP call."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "test_token",
            "expires_in": 86400,
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        with patch.dict(
            os.environ,
            {
                "KIS_IS_PAPER": "true",
                "KIS_CMW_APP_KEY_PAPER": "test_key",
                "KIS_CMW_APP_SECRET_PAPER": "test_secret",
                "KIS_CMW_ACCOUNT_NUMBER_PAPER": "12345",
            },
        ):
            client = KisClient()
            token1 = client.get_token()
            token2 = client.get_token()
            self.assertEqual(token1, token2)
            self.assertEqual(mock_post.call_count, 1)
