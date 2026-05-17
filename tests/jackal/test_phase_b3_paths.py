import unittest


class PhaseB3PathsTests(unittest.TestCase):
    def test_adapter_orca_baseline_uses_shared_paths(self):
        """jackal.adapter.ORCA_BASELINE이 shared.paths.BASELINE_FILE과 같은 객체"""
        from apps.jackal.pipeline.adapter import ORCA_BASELINE
        from shared.paths import BASELINE_FILE
        self.assertEqual(ORCA_BASELINE, BASELINE_FILE)

    def test_adapter_orca_memory_uses_shared_paths(self):
        from apps.jackal.pipeline.adapter import ORCA_MEMORY
        from shared.paths import MEMORY_FILE
        self.assertEqual(ORCA_MEMORY, MEMORY_FILE)

    def test_adapter_jackal_weights_uses_shared_paths(self):
        from apps.jackal.pipeline.adapter import _JACKAL_WEIGHTS
        from shared.paths import JACKAL_WEIGHTS_FILE
        self.assertEqual(_JACKAL_WEIGHTS, JACKAL_WEIGHTS_FILE)

    def test_adapter_jackal_news_uses_shared_paths(self):
        from apps.jackal.pipeline.adapter import JACKAL_NEWS
        from shared.paths import JACKAL_NEWS_FILE
        self.assertEqual(JACKAL_NEWS, JACKAL_NEWS_FILE)

    def test_shield_usage_log_uses_shared_paths(self):
        from apps.jackal.shield import _USAGE_LOG
        from shared.paths import JACKAL_USAGE_LOG_FILE
        self.assertEqual(_USAGE_LOG, JACKAL_USAGE_LOG_FILE)

    def test_compact_usage_log_uses_shared_paths(self):
        from apps.jackal.compact import _USAGE_LOG
        from shared.paths import JACKAL_USAGE_LOG_FILE
        self.assertEqual(_USAGE_LOG, JACKAL_USAGE_LOG_FILE)

    def test_jackal_weights_still_in_jackal_dir(self):
        """jackal/jackal_weights.json 위치 변경 안 됨 (운영 데이터 안전)"""
        from apps.jackal.pipeline.adapter import _JACKAL_WEIGHTS
        self.assertEqual(_JACKAL_WEIGHTS.name, "jackal_weights.json")
        self.assertEqual(_JACKAL_WEIGHTS.parent.name, "jackal")

    def test_usage_log_still_in_jackal_dir(self):
        """jackal/jackal_usage_log.json 위치 변경 안 됨"""
        from apps.jackal.shield import _USAGE_LOG
        self.assertEqual(_USAGE_LOG.name, "jackal_usage_log.json")
        self.assertEqual(_USAGE_LOG.parent.name, "jackal")


if __name__ == "__main__":
    unittest.main()
