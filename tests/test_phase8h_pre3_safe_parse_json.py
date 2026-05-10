import unittest

from jackal.hunter import _safe_parse_json


class Phase8hPre3SafeParseJsonTests(unittest.TestCase):
    def test_simple_json(self):
        result = _safe_parse_json('{"devil_score": 70, "verdict": "oppose"}')
        self.assertEqual(result["devil_score"], 70)

    def test_fenced_json(self):
        text = """
        Analysis:
        ```json
        {"devil_score": 30, "verdict": "partial"}
        ```
        """
        result = _safe_parse_json(text, schema_keys=["devil_score"])
        self.assertEqual(result["devil_score"], 30)

    def test_fenced_no_json_marker(self):
        text = """
        ````
        {"devil_score": 50}
        ````
        """
        result = _safe_parse_json(text)
        self.assertEqual(result["devil_score"], 50)

    def test_multiple_objects_prefers_schema_match(self):
        text = """
        Example: {"example": "value"}
        Result:
        {"devil_score": 40, "verdict": "oppose", "main_risk": "crowded trade"}
        """
        result = _safe_parse_json(text, schema_keys=["devil_score"])
        self.assertEqual(result["devil_score"], 40)
        self.assertEqual(result["main_risk"], "crowded trade")

    def test_text_with_explanation(self):
        text = """
        Market context considered.
        {"devil_score": 60, "verdict": "weak oppose"}
        Additional comments after JSON.
        """
        result = _safe_parse_json(text, schema_keys=["devil_score"])
        self.assertEqual(result["devil_score"], 60)

    def test_trailing_comma(self):
        result = _safe_parse_json('{"devil_score": 70, "verdict": "oppose",}')
        self.assertEqual(result["devil_score"], 70)

    def test_truncated_json(self):
        text = '{"devil_score": 70, "verdict": "oppose", "main_risk": "late chase"'
        result = _safe_parse_json(text)
        self.assertEqual(result.get("devil_score"), 70)

    def test_empty_text(self):
        self.assertEqual(_safe_parse_json(""), {})

    def test_no_json(self):
        self.assertEqual(_safe_parse_json("LLM response without JSON"), {})

    def test_nested_object(self):
        text = '{"devil_score": 70, "details": {"key": "value"}}'
        result = _safe_parse_json(text)
        self.assertEqual(result["devil_score"], 70)
        self.assertEqual(result["details"]["key"], "value")

    def test_schema_prefers_analyst_result_over_example(self):
        text = """
        Example: {"devil_score": 90, "verdict": "oppose"}
        Final:
        {"analyst_score": 82, "signals_fired": ["volume"], "bull_case": "setup"}
        """
        result = _safe_parse_json(text, schema_keys=["analyst_score", "signals_fired"])
        self.assertEqual(result["analyst_score"], 82)


if __name__ == "__main__":
    unittest.main()
