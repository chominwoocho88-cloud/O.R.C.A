import os
import sys
import unittest
from unittest.mock import patch

from apps.jackal import core, scanner
from apps.orca import backtest


ENTRYPOINTS = (
    ("jackal_core", core._check_llm_credentials),
    ("jackal_scanner", scanner._check_llm_credentials),
    ("orca_backtest", backtest._check_llm_credentials),
)


class LLMEntrypointFailFastTest(unittest.TestCase):
    def _without_anthropic_key(self):
        patcher = patch.dict(os.environ, {}, clear=False)
        patched_env = patcher.__enter__()
        patched_env.pop("ANTHROPIC_API_KEY", None)
        self.addCleanup(patcher.__exit__, None, None, None)

    def test_entrypoints_fail_fast_before_work_when_key_missing(self):
        self._without_anthropic_key()

        with patch.object(core, "JackalCore") as jackal_core:
            with patch.object(sys, "argv", ["jackal-core"]):
                with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY environment variable is required"):
                    core.main()
            jackal_core.assert_not_called()

        with patch.object(scanner, "run_scan") as run_scan:
            with patch.object(sys, "argv", ["jackal-scanner"]):
                with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY environment variable is required"):
                    scanner.main()
            run_scan.assert_not_called()

        with patch.object(backtest, "start_backtest_session") as start_backtest_session:
            with patch.object(sys, "argv", ["orca-backtest"]):
                with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY environment variable is required"):
                    backtest.main()
            start_backtest_session.assert_not_called()

    def test_empty_or_whitespace_key_fails_fast(self):
        for name, check_credentials in ENTRYPOINTS:
            for value in ("", "   "):
                with self.subTest(entrypoint=name, value=repr(value)):
                    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": value}, clear=False):
                        with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY environment variable is required"):
                            check_credentials()

    def test_present_key_passes(self):
        for name, check_credentials in ENTRYPOINTS:
            with self.subTest(entrypoint=name):
                with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
                    check_credentials()


if __name__ == "__main__":
    unittest.main()
