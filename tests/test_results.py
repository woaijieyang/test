import sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from result_contract import aggregate, render


class Results(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "run_id": "synthetic-test-only",
            "claim_scope": "fixture",
            "expected_tasks": [{"task_key": str(i), "dataset": "r2r"} for i in range(3)],
        }
        self.rows = [
            {
                "task_key": str(i),
                "dataset": "r2r",
                "status": "completed",
                "metrics": {
                    "sr": int(i == 0),
                    "spl": float(i == 0),
                    "ndtw": 0.5,
                    "ne": float(i + 1),
                    "oracle_sr": 1.0,
                },
            }
            for i in range(3)
        ]

    def test_per_episode_mean_not_shard_mean(self):
        value = aggregate(self.manifest, self.rows)
        self.assertAlmostEqual(value["datasets"]["r2r"]["metrics"]["sr"], 1 / 3)
        self.assertEqual(value["datasets"]["r2r"]["metrics"]["ne"], 2)

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            aggregate(self.manifest, self.rows + [self.rows[0]])

    def test_missing_not_complete(self):
        value = aggregate(self.manifest, self.rows[:-1])
        self.assertFalse(value["complete"])
        self.assertEqual(value["missing"], ["2"])

    def test_infra_failure_not_navigation_failure(self):
        self.rows[2]["status"] = "interrupted"
        v = aggregate(self.manifest, self.rows)
        self.assertFalse(v["complete"])
        self.assertEqual(v["runtime_errors"], ["2"])
        self.assertEqual(v["datasets"]["r2r"]["navigation_failures"], 1)

    def test_nonfinite_not_silently_filtered(self):
        for value in (None, float("inf"), float("nan"), -1, True):
            self.rows[0]["metrics"]["ne"] = value
            with self.assertRaises(ValueError):
                aggregate(self.manifest, self.rows)

    def test_wrong_dataset_rejected(self):
        self.rows[0]["dataset"] = "rxr"
        with self.assertRaises(ValueError):
            aggregate(self.manifest, self.rows)

    def test_empty_registry_has_no_formal_rows(self):
        table, reports = render({"records": []})
        self.assertIn("当前无", table)
        self.assertEqual(reports, {})


if __name__ == "__main__":
    unittest.main()
