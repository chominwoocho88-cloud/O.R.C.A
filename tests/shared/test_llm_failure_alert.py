from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
import builtins
from unittest.mock import Mock, patch


class LLMFailureAlertTests(unittest.TestCase):
    def setUp(self) -> None:
        self.alert = importlib.import_module("shared.llm.failure_alert")
        self.alert.reset_for_testing()

    def tearDown(self) -> None:
        self.alert.reset_for_testing()

    def _install_fake_transport(self, send_message: Mock) -> None:
        module = types.ModuleType("orca.notify_transport")
        module.send_message = send_message
        sys.modules["orca.notify_transport"] = module

    def _failure(self, **overrides):
        failure = {
            "error_type": "retry_exhausted",
            "call_site": "orca.reporter",
            "model": "claude-test",
            "attempt": 2,
            "message": "boom",
        }
        failure.update(overrides)
        return failure

    def test_missing_env_keeps_alerts_enabled(self):
        send_message = Mock(return_value=True)
        previous = sys.modules.get("orca.notify_transport")
        try:
            self._install_fake_transport(send_message)
            with patch.dict(os.environ, {}, clear=True):
                self.alert.maybe_alert_failure(self._failure())
        finally:
            if previous is None:
                sys.modules.pop("orca.notify_transport", None)
            else:
                sys.modules["orca.notify_transport"] = previous

        send_message.assert_called_once()

    def test_env_zero_disables_alert(self):
        send_message = Mock(return_value=True)
        previous = sys.modules.get("orca.notify_transport")
        try:
            self._install_fake_transport(send_message)
            with patch.dict(os.environ, {"LLM_FAILURE_TELEGRAM_ALERTS": "0"}, clear=True):
                self.alert.maybe_alert_failure(self._failure())
        finally:
            if previous is None:
                sys.modules.pop("orca.notify_transport", None)
            else:
                sys.modules["orca.notify_transport"] = previous

        send_message.assert_not_called()

    def test_per_process_throttle_sends_once(self):
        send_message = Mock(return_value=True)
        previous = sys.modules.get("orca.notify_transport")
        try:
            self._install_fake_transport(send_message)
            self.alert.maybe_alert_failure(self._failure(call_site="orca.one"))
            self.alert.maybe_alert_failure(self._failure(call_site="orca.two"))
        finally:
            if previous is None:
                sys.modules.pop("orca.notify_transport", None)
            else:
                sys.modules["orca.notify_transport"] = previous

        send_message.assert_called_once()
        self.assertIn("orca.one", send_message.call_args.args[0])

    def test_send_exception_is_fail_open(self):
        send_message = Mock(side_effect=RuntimeError("telegram down"))
        previous = sys.modules.get("orca.notify_transport")
        try:
            self._install_fake_transport(send_message)
            self.alert.maybe_alert_failure(self._failure())
        finally:
            if previous is None:
                sys.modules.pop("orca.notify_transport", None)
            else:
                sys.modules["orca.notify_transport"] = previous

        send_message.assert_called_once()

    def test_import_failure_is_fail_open(self):
        original_import = builtins.__import__

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "orca.notify_transport":
                raise ImportError("blocked")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=guarded_import):
            self.alert.maybe_alert_failure(self._failure())

    def test_message_format_includes_context_and_truncates(self):
        long_message = "x" * 350
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_WORKFLOW": "ORCA Daily"}, clear=True):
            message = self.alert._format_message(
                self._failure(
                    error_type="auth_failed",
                    call_site="orca.<bad>",
                    model="claude-test",
                    attempt=1,
                    message=long_message,
                )
            )

        self.assertIn("LLM final failure", message)
        self.assertIn("auth_failed", message)
        self.assertIn("orca.&lt;bad&gt;", message)
        self.assertIn("claude-test", message)
        self.assertIn("attempt: <code>1</code>", message)
        self.assertIn("run_id: <code>123</code>", message)
        self.assertIn("workflow: <code>ORCA Daily</code>", message)
        self.assertIn("...", message)
        self.assertNotIn(long_message, message)


if __name__ == "__main__":
    unittest.main()
