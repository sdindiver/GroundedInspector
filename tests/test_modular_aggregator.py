import unittest

from grounded_inspector import modular_pipeline


class ModularAggregatorTests(unittest.TestCase):
    def bundle(self):
        return {
            "part": "Bracket",
            "image": "input.png",
            "defects": [
                {"category": "line_mark", "scope": "global", "severity": 3, "display_name": "Line Mark"},
                {"category": "dark_spot", "scope": "global", "severity": 1, "display_name": "Dark Spots"},
            ],
        }

    def test_clear_has_no_defects(self):
        verdict = modular_pipeline._aggregate(
            self.bundle(),
            {"status": "CLEAR", "facts": {}, "evidence": {}},
            [
                {"defect": "line_mark", "status": "CLEAR", "evidence": "none", "locations": []},
                {"defect": "dark_spot", "status": "CLEAR", "evidence": "none", "locations": []},
            ],
        )
        self.assertEqual(verdict["result"], "OK")
        self.assertEqual(verdict["defects"], [])

    def test_defect_aggregates_independent_results(self):
        verdict = modular_pipeline._aggregate(
            self.bundle(),
            {"status": "CLEAR", "facts": {}, "evidence": {}},
            [
                {
                    "defect": "line_mark",
                    "status": "DEFECT",
                    "evidence": "continuous line",
                    "locations": [
                        {"bbox": [0.1, 0.2, 0.3, 0.1], "confidence": 0.9, "reason": "continuous"}
                    ],
                },
                {"defect": "dark_spot", "status": "CLEAR", "evidence": "none", "locations": []},
            ],
        )
        self.assertEqual(verdict["result"], "DEFECT")
        self.assertEqual([d["category"] for d in verdict["defects"]], ["line_mark"])
        self.assertEqual(verdict["primary"], "line_mark")

    def test_unresolved_checkpoint_wins_over_defect(self):
        verdict = modular_pipeline._aggregate(
            self.bundle(),
            {"status": "CLEAR", "facts": {}, "evidence": {}},
            [
                {
                    "defect": "line_mark",
                    "status": "DEFECT",
                    "evidence": "continuous line",
                    "locations": [
                        {"bbox": [0.1, 0.2, 0.3, 0.1], "confidence": 0.9, "reason": "continuous"}
                    ],
                },
                {
                    "defect": "dark_spot",
                    "status": "NEEDS_REVIEW",
                    "evidence": "insufficient",
                    "locations": [],
                },
            ],
        )
        self.assertEqual(verdict["result"], "NEEDS_REVIEW")
        self.assertIsNone(verdict["primary"])
        self.assertEqual([d["category"] for d in verdict["defects"]], ["line_mark"])


if __name__ == "__main__":
    unittest.main()
