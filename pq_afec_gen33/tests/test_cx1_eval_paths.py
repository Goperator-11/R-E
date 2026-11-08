import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True

from experiments.v33 import cx1_eval

ROOT = Path(__file__).resolve().parents[1]
LOCAL_PATH = re.compile(r"[A-Za-z]:[\\/]|/home/|/mnt/[a-z]/|AppData|scratchpad|codex_handoff[\\/]")


class Cx1EvalInputs(unittest.TestCase):
    def test_runs_root_comes_from_argument_or_environment(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            with mock.patch.dict(os.environ):
                os.environ.pop(cx1_eval.RUNS_ENV, None)
                with self.assertRaises(ValueError):
                    cx1_eval.runs_root(None)
                os.environ[cx1_eval.RUNS_ENV] = second
                self.assertEqual(cx1_eval.runs_root(None), Path(second))
                self.assertEqual(cx1_eval.runs_root(first), Path(first))
            with self.assertRaises(FileNotFoundError):
                cx1_eval.runs_root(str(Path(first) / "missing"))

    def test_recorded_table_and_reference_labels_are_relative(self):
        with tempfile.TemporaryDirectory() as directory:
            runs = Path(directory) / "runs"
            for name in cx1_eval.TABLE_RUNS:
                (runs / name).mkdir(parents=True)
                (runs / name / "table.json").write_text(json.dumps({"context_id": name, "action": [0, 0, 1]}),
                                                        encoding="utf-8")
            extra = Path(directory) / "work" / "extra_tables"
            extra.mkdir(parents=True)
            _, counts = cx1_eval.load_tables(runs, {"work:extra_tables": extra})
            self.assertEqual(counts, {"runs:" + cx1_eval.TABLE_RUNS[0]: 1, "runs:" + cx1_eval.TABLE_RUNS[1]: 1,
                                      "work:extra_tables": 0})
            frozen = runs / cx1_eval.V32_RAW_RUN / "B1"
            frozen.mkdir(parents=True)
            (frozen / "seed00007.json").write_text(json.dumps({
                "seed": 7, "n": 2, "action_counts": [{"context_id": "c", "action": [0, 0, 1], "n": 2}],
                "summary": {"mean_hct_ms": 50.0}}), encoding="utf-8")
            result = cx1_eval.compare_v32([{"cell": "B1", "seed": 7, "n": 2, "counts": [["c", [0, 0, 1], 2]],
                                            "mean_hct": 50.0}], runs)
            self.assertEqual(result["reference"], "runs:" + cx1_eval.V32_RAW_RUN)
            self.assertEqual(result["counts_equal"], 1)
            self.assertIsNone(LOCAL_PATH.search(json.dumps([counts, result])))

    def test_all_needs_runs_before_creating_work(self):
        with mock.patch.dict(os.environ), tempfile.TemporaryDirectory() as directory:
            os.environ.pop(cx1_eval.RUNS_ENV, None)
            work = Path(directory) / "work"
            with self.assertRaises(ValueError):
                cx1_eval.main(["all", "--work", str(work), "--parts", "w1"])
            self.assertFalse(work.exists())

    def test_tool_and_record_carry_no_local_absolute_paths(self):
        for relative in ("experiments/v33/cx1_eval.py", "g3/v33/CX1_eval_v1.json"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIsNone(LOCAL_PATH.search(text), relative)


if __name__ == "__main__":
    unittest.main()
