import os
import unittest
from unittest.mock import MagicMock, patch


class JackalBuildInfoTests(unittest.TestCase):
    def test_build_info_imports_in_jackal(self):
        """jackal에서 shared.build_info import 가능"""
        from shared.build_info import get_build_info

        self.assertTrue(callable(get_build_info))

    def test_jackal_hunter_build_in_message(self):
        """jackal.hunter 텔레그램 메시지에 build 포함"""
        from jackal import hunter

        response = MagicMock()
        response.json.return_value = {"ok": True}
        with patch.dict(os.environ, {"GITHUB_SHA": "test12345abcdef"}):
            with patch.object(hunter, "TELEGRAM_TOKEN", "token"):
                with patch.object(hunter, "TELEGRAM_CHAT_ID", "chat"):
                    with patch("jackal.hunter.httpx.post", return_value=response) as mock_post:
                        self.assertTrue(hunter._send_telegram("hunter alert"))

        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("<code>build: test123</code>", payload["text"])

    def test_jackal_scanner_build_in_message(self):
        """jackal.scanner 텔레그램 메시지에 build 포함"""
        from jackal import scanner

        response = MagicMock()
        response.json.return_value = {"ok": True}
        with patch.dict(os.environ, {"GITHUB_SHA": "test12345abcdef"}):
            with patch.object(scanner, "TELEGRAM_TOKEN", "token"):
                with patch.object(scanner, "TELEGRAM_CHAT_ID", "chat"):
                    with patch("jackal.scanner.httpx.post", return_value=response) as mock_post:
                        self.assertTrue(scanner._send_telegram("scanner alert"))

        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("<code>build: test123</code>", payload["text"])

    def test_jackal_tracker_build_in_message(self):
        """jackal.tracker 텔레그램 메시지에 build 포함"""
        from jackal import tracker

        stats = {
            "confirmed": 1,
            "partial": 0,
            "weight_changes": ["AAPL +0.1"],
        }
        with patch.dict(
            os.environ,
            {
                "GITHUB_SHA": "test12345abcdef",
                "TELEGRAM_TOKEN": "token",
                "TELEGRAM_CHAT_ID": "chat",
            },
        ):
            with patch("httpx.post") as mock_post:
                tracker._send_tracker_summary(stats)

        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("<code>build: test123</code>", payload["text"])

    def test_build_info_consistency(self):
        """ORCA와 JACKAL이 같은 build_info 사용"""
        from shared.build_info import get_build_info
        from orca.notify import get_build_info as orca_func

        with patch.dict(os.environ, {"GITHUB_SHA": "test12345"}):
            self.assertEqual(orca_func(), get_build_info())


if __name__ == "__main__":
    unittest.main()
