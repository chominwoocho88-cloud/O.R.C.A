import unittest

from jackal.hunter import _final


class Phase8h16aDiagLoggingTests(unittest.TestCase):
    def test_diag_normal_calculation(self):
        analyst = {
            "analyst_score": 78,
            "day1_score": 60,
            "swing_score": 70,
            "swing_setup": "반등가능",
            "swing_type": "기술적과매도",
        }
        devil = {"devil_score": 62, "verdict": "부분동의"}

        final = _final(analyst, devil)
        diag = final["diag"]

        self.assertIsNone(diag["block_reason"])
        self.assertEqual(diag["analyst_score"], 78)
        self.assertEqual(diag["day1_score"], 60)
        self.assertEqual(diag["swing_score"], 70)
        self.assertEqual(diag["devil_score"], 62)
        self.assertEqual(diag["raw_score"], 64.5)
        self.assertEqual(diag["penalty"], 8.0)
        self.assertEqual(diag["before_adjust"], final["final_score"])
        self.assertEqual(diag["weights"], {"day1": 0.55, "swing": 0.45})

    def test_diag_dead_cat_block(self):
        analyst = {"analyst_score": 78, "day1_score": 60, "swing_score": 70}
        devil = {"devil_score": 62, "verdict": "부분동의", "is_dead_cat": True}

        final = _final(analyst, devil)
        diag = final["diag"]

        self.assertEqual(final["final_score"], 20)
        self.assertEqual(diag["block_reason"], "dead_cat")
        self.assertIsNone(diag["raw_score"])
        self.assertEqual(diag["before_adjust"], 20)

    def test_diag_thesis_killer_block(self):
        analyst = {"analyst_score": 78, "day1_score": 60, "swing_score": 70}
        devil = {"devil_score": 62, "verdict": "부분동의", "thesis_killer_hit": True}

        final = _final(analyst, devil)

        self.assertEqual(final["diag"]["block_reason"], "thesis_killer")

    def test_diag_devil_block(self):
        analyst = {"analyst_score": 78, "day1_score": 60, "swing_score": 70}
        devil = {"devil_score": 75, "verdict": "반대"}

        final = _final(analyst, devil)
        diag = final["diag"]

        self.assertEqual(final["final_score"], 25)
        self.assertEqual(diag["block_reason"], "devil_block")
        self.assertEqual(diag["devil_score"], 75)
        self.assertEqual(diag["before_adjust"], 25)


if __name__ == "__main__":
    unittest.main()
