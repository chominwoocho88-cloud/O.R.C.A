"""Contract invariant tests for PR 1-5 and Phase 5.

These tests lock in the repository contracts documented in
docs/analysis/2026-04-22_repository_review.md Section 6 P1-1.
If any test fails, a committed contract has drifted and needs
explicit review before further refactors proceed.
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _parse_module(path: Path) -> ast.Module:
    return ast.parse(_read_text(path), filename=str(path))


def _find_assignment(module: ast.Module, name: str) -> ast.Assign:
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return node
    raise AssertionError(f"Could not find assignment for {name!r}")


def _get_function_source(path: Path, function_name: str) -> str:
    source = _read_text(path)
    lines = source.splitlines()
    module = ast.parse(source, filename=str(path))
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"Could not find function {function_name!r} in {path}")


def _import_module(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _make_httpx_stub() -> types.ModuleType:
    httpx = types.ModuleType("httpx")

    def _unexpected_httpx_call(*args, **kwargs):
        raise AssertionError("Network access is not allowed in contract tests")

    httpx.get = _unexpected_httpx_call
    httpx.post = _unexpected_httpx_call
    return httpx


def _exercise_market_data_contract(
    *,
    yahoo_quality: str,
    fear_greed: dict | None,
) -> dict:
    """Run fetch_all_market_data with fully stubbed dependencies."""
    httpx_stub = _make_httpx_stub()
    notify_stub = types.ModuleType("orca.notify")
    notify_stub.send_message = lambda *args, **kwargs: True

    base_fg = fear_greed or {
        "value": 55,
        "rating": "Neutral",
        "prev_close": 52,
        "source": "fear_greed_chart",
        "confidence": "보통",
    }
    base_pcr = {
        "pcr_spy": 0.9,
        "pcr_qqq": 0.95,
        "pcr_avg": 0.925,
        "pcr_signal": "중립",
    }
    base_krx = {
        "foreign_net": "1000",
        "institution_net": "-200",
        "individual_net": "-800",
        "foreign_buy": "5000",
        "foreign_sell": "4000",
        "source": "krx_api",
        "date": "2026-04-22",
    }
    base_fred = {
        "vix_fred": 21.0,
        "hy_spread": 3.1,
        "yield_curve": -0.2,
        "consumer_sent": 76.0,
        "rrp": 300.0,
        "dxy": 101.5,
        "fred_source": True,
    }
    base_fsc = {
        "samsung_fsc": 1.0,
        "sk_hynix_fsc": 2.0,
        "gold_price": 2300.0,
        "oil_price_diesel": 1600.0,
        "oil_price_gasoline": 1700.0,
        "fsc_source": True,
    }

    sys.modules.pop("orca.data", None)
    with patch.dict(sys.modules, {"httpx": httpx_stub, "orca.notify": notify_stub}):
        data = importlib.import_module("orca.data")
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_file = Path(tmpdir) / "orca_market_data.json"
            with patch.object(data, "DATA_FILE", temp_file), patch.object(
                data, "_get_market_status", return_value=("OPEN", "contract-test")
            ), patch.object(
                data, "check_volatility_alert", return_value=False
            ), patch.object(
                data,
                "fetch_yahoo_data",
                return_value={"data_quality": yahoo_quality},
            ), patch.object(
                data,
                "fetch_fear_greed",
                return_value=base_fg,
            ), patch.object(
                data,
                "fetch_put_call_ratio",
                return_value=base_pcr,
            ), patch.object(
                data,
                "fetch_krx_flow",
                return_value=base_krx,
            ), patch.object(
                data,
                "fetch_fred_indicators",
                return_value=base_fred,
            ), patch.object(
                data,
                "fetch_fsc_data",
                return_value=base_fsc,
            ), patch.object(
                data,
                "fetch_korea_news",
                return_value=["headline"],
            ):
                result = data.fetch_all_market_data()

            persisted = json.loads(temp_file.read_text(encoding="utf-8"))
            if result != persisted:
                raise AssertionError("Persisted market-data payload differs from return value")

    sys.modules.pop("orca.data", None)
    return result


class TestPR1HealthCodes(unittest.TestCase):
    """PR 1: HealthTracker 10 codes invariant."""

    EXPECTED_CODES = {
        "state_db_unavailable",
        "state_payload_invalid",
        "cost_alert_failed",
        "weight_update_failed",
        "candidate_review_unavailable",
        "probability_summary_unavailable",
        "pattern_db_update_failed",
        "dashboard_generation_failed",
        "external_data_degraded",
        "notification_failed",
    }

    def test_exactly_10_unique_health_codes_exist(self):
        actual = set()
        for py_file in (ROOT / "orca").rglob("*.py"):
            module = _parse_module(py_file)
            for node in ast.walk(module):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                first_arg = node.args[0]
                if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
                    continue
                func = node.func
                if isinstance(func, ast.Name) and func.id == "_record_health_event":
                    actual.add(first_arg.value)
                    continue
                if isinstance(func, ast.Attribute) and func.attr in {"record", "record_exception"}:
                    base = func.value
                    if isinstance(base, ast.Name) and base.id in {"health_tracker", "health"}:
                        actual.add(first_arg.value)

        self.assertEqual(
            actual,
            self.EXPECTED_CODES,
            "PR 1 health codes drifted. "
            f"Missing={sorted(self.EXPECTED_CODES - actual)}, "
            f"Extra={sorted(actual - self.EXPECTED_CODES)}, "
            f"Actual={sorted(actual)}",
        )
        self.assertEqual(len(actual), 10, f"PR 1 requires exactly 10 unique codes, found {len(actual)}")


class TestPR2LearningPolicy(unittest.TestCase):
    """PR 2: learning_policy constants invariant."""

    def test_learning_policy_constants_are_unchanged(self):
        learning_policy = _import_module("orca.learning_policy")

        self.assertEqual(
            learning_policy.MIN_SAMPLES,
            5,
            f"PR 2 drift: MIN_SAMPLES={learning_policy.MIN_SAMPLES!r}, expected 5",
        )
        self.assertEqual(
            learning_policy.PRIOR_WINS,
            2,
            f"PR 2 drift: PRIOR_WINS={learning_policy.PRIOR_WINS!r}, expected 2",
        )
        self.assertEqual(
            learning_policy.PRIOR_TOTAL,
            4,
            f"PR 2 drift: PRIOR_TOTAL={learning_policy.PRIOR_TOTAL!r}, expected 4",
        )
        self.assertAlmostEqual(
            learning_policy.TRUSTED_EFFECTIVE_WIN_RATE,
            0.58,
            msg=(
                "PR 2 drift: TRUSTED_EFFECTIVE_WIN_RATE="
                f"{learning_policy.TRUSTED_EFFECTIVE_WIN_RATE!r}, expected 0.58"
            ),
        )
        self.assertAlmostEqual(
            learning_policy.CAUTIOUS_EFFECTIVE_WIN_RATE,
            0.46,
            msg=(
                "PR 2 drift: CAUTIOUS_EFFECTIVE_WIN_RATE="
                f"{learning_policy.CAUTIOUS_EFFECTIVE_WIN_RATE!r}, expected 0.46"
            ),
        )


class TestPR3MainThinCoordinator(unittest.TestCase):
    """PR 3: main.py thin coordinator invariant."""

    def test_main_py_stays_under_50_lines(self):
        main_path = ROOT / "orca" / "main.py"
        line_count = len(_read_text(main_path).splitlines())
        self.assertLessEqual(
            line_count,
            50,
            f"PR 3 drift: orca/main.py is {line_count} lines; limit is 50",
        )


class TestPR4ReviewScoreWeights(unittest.TestCase):
    """PR 4: candidate review scorecard weights invariant."""

    EXPECTED_WEIGHTS = {
        "market_bias": 0.15,
        "signal_family_history": 0.30,
        "quality": 0.20,
        "theme_match": 0.15,
        "devil_penalty": 0.10,
        "thesis_killer_penalty": 0.10,
    }

    def test_review_score_weights_match_committed_contract(self):
        module = _parse_module(ROOT / "orca" / "analysis.py")
        assign = _find_assignment(module, "_REVIEW_SCORE_WEIGHTS")
        actual = ast.literal_eval(assign.value)

        self.assertEqual(
            actual,
            self.EXPECTED_WEIGHTS,
            f"PR 4 drift: _REVIEW_SCORE_WEIGHTS={actual!r}, expected {self.EXPECTED_WEIGHTS!r}",
        )
        self.assertAlmostEqual(
            sum(actual.values()),
            1.0,
            places=9,
            msg=f"PR 4 drift: weight sum is {sum(actual.values())!r}, expected 1.0",
        )


class TestPR5ExternalDataVisibility(unittest.TestCase):
    """PR 5: data_quality tiers and failed_sources visibility invariant."""

    def test_external_data_visibility_contract_holds(self):
        scenarios = {
            "ok": _exercise_market_data_contract(yahoo_quality="ok", fear_greed=None),
            "degraded": _exercise_market_data_contract(
                yahoo_quality="ok",
                fear_greed={
                    "value": "N/A",
                    "rating": "N/A",
                    "prev_close": "N/A",
                    "source": "unknown",
                    "confidence": "낮음",
                },
            ),
            "poor": _exercise_market_data_contract(yahoo_quality="poor", fear_greed=None),
        }

        for expected_quality, payload in scenarios.items():
            with self.subTest(data_quality=expected_quality):
                self.assertEqual(
                    payload.get("data_quality"),
                    expected_quality,
                    "PR 5 drift: unexpected data_quality tier "
                    f"for {expected_quality} scenario: {payload.get('data_quality')!r}",
                )
                self.assertIn(
                    payload.get("data_quality"),
                    {"ok", "degraded", "poor"},
                    f"PR 5 drift: invalid data_quality value {payload.get('data_quality')!r}",
                )
                self.assertIn(
                    "failed_sources",
                    payload,
                    f"PR 5 drift: failed_sources missing from payload for {expected_quality} scenario",
                )
                self.assertIsInstance(
                    payload["failed_sources"],
                    list,
                    "PR 5 drift: failed_sources must be a list, "
                    f"got {type(payload['failed_sources']).__name__}",
                )

        report_path = ROOT / "reports" / "2026-04-22_morning.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertIn(
            report.get("data_quality"),
            {"ok", "degraded", "poor"},
            f"PR 5 drift: latest report data_quality is {report.get('data_quality')!r}",
        )
        self.assertIn("failed_sources", report, "PR 5 drift: latest report is missing failed_sources")
        self.assertIsInstance(
            report["failed_sources"],
            list,
            f"PR 5 drift: latest report failed_sources is {type(report['failed_sources']).__name__}, expected list",
        )


class TestPhase5RoutingHelpers(unittest.TestCase):
    """Phase 5: routing helper availability invariant."""

    def test_routing_helpers_are_importable_and_callable(self):
        state = _import_module("orca.state")

        self.assertTrue(
            any(callable(getattr(state, name, None)) for name in ("_connect_orca", "_connect")),
            "Phase 5 drift: expected _connect_orca or legacy _connect to be importable and callable",
        )
        self.assertTrue(
            callable(getattr(state, "_connect_jackal", None)),
            "Phase 5 drift: _connect_jackal is missing or not callable",
        )
        self.assertTrue(
            callable(getattr(state, "checkpoint_jackal_db", None)),
            "Phase 5 drift: checkpoint_jackal_db is missing or not callable",
        )


class TestPhase5WorkflowContracts(unittest.TestCase):
    """Phase 5: workflow state persistence invariant."""

    WORKFLOW_FILES = {
        ".github/workflows/orca_daily.yml",
        ".github/workflows/orca_jackal.yml",
        ".github/workflows/jackal_tracker.yml",
        ".github/workflows/jackal_scanner.yml",
    }

    def test_workflows_include_jackal_state_and_checkpoint_call(self):
        for relative_path in sorted(self.WORKFLOW_FILES):
            with self.subTest(workflow=relative_path):
                path = ROOT / relative_path
                text = _read_text(path)
                self.assertIn(
                    "data/jackal_state.db",
                    text,
                    f"Phase 5 drift: {relative_path} no longer includes data/jackal_state.db",
                )
                self.assertIn(
                    "checkpoint_jackal_db",
                    text,
                    f"Phase 5 drift: {relative_path} no longer calls checkpoint_jackal_db",
                )


class TestPhase52PhaseWriteMitigation(unittest.TestCase):
    """Phase 5: 2-phase write best-effort semantics invariant."""

    EXPECTED_FUNCTIONS = (
        "record_jackal_shadow_signal",
        "resolve_jackal_shadow_signal",
        "sync_jackal_live_events",
    )

    def test_2phase_write_functions_keep_best_effort_secondary_semantics(self):
        state_path = ROOT / "orca" / "state.py"
        for function_name in self.EXPECTED_FUNCTIONS:
            with self.subTest(function=function_name):
                source = _get_function_source(state_path, function_name)
                self.assertIn(
                    "Phase 5 Path B",
                    source,
                    f"Phase 5 drift: {function_name} lost the Phase 5 Path B note",
                )
                self.assertIn(
                    "Secondary write to orca_state.db",
                    source,
                    f"Phase 5 drift: {function_name} no longer documents the secondary write",
                )
                self.assertIn(
                    "Primary (jackal_state.db) already succeeded.",
                    source,
                    f"Phase 5 drift: {function_name} no longer documents primary-first semantics",
                )
                self.assertIn(
                    "cross-DB secondary write failed in ",
                    source,
                    f"Phase 5 drift: {function_name} no longer logs cross-DB secondary write failure prefix",
                )
                self.assertIn(
                    f"{function_name}: ",
                    source,
                    f"Phase 5 drift: {function_name} no longer includes its function-specific warning label",
                )


if __name__ == "__main__":
    unittest.main()
