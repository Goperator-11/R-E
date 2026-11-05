import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gate_l1_go", ROOT / "experiments/gate_l1_go.py")
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class L1GateTests(unittest.TestCase):
    def fixture(self):
        return dict(state=dict(v=4, post=[[0.1, 0.9]], w=[1.0],
                               S_hist=[8500.0], hct={"0,0,0": [80.0]},
                               stats=dict(datagram=1)),
                    info=dict(grade=1, updated=True, cut1_ms=80.0, skip=None),
                    likelihood=[0.2, 0.8])

    def test_equal(self):
        value = self.fixture()
        result = GATE.compare(value, copy.deepcopy(value))
        self.assertTrue(result["passed"])
        self.assertEqual(result["counts"]["leaves"], result["counts"]["bit_exact"])

    def test_mutations_are_rejected(self):
        mutations = [
            lambda x: x["state"].update(v=3),
            lambda x: x["state"]["stats"].update(datagram=0),
            lambda x: x["state"].update(post=[[0.100001, 0.899999]]),
            lambda x: x["state"].update(w=[0.9999]),
            lambda x: x["state"].update(S_hist=[8500.0 + 1e-10]),
            lambda x: x["state"].update(hct={"0,0,0": [80.0 + 1e-10]}),
            lambda x: x["info"].update(grade=2),
            lambda x: x["info"].update(updated=1),
            lambda x: x["info"].update(skip="no_ctx"),
            lambda x: x["info"].update(cut1_ms=80.00001),
            lambda x: x.update(likelihood=[0.200001, 0.799999]),
            lambda x: x.update(likelihood=[0.2]),
            lambda x: x["state"].pop("stats"),
            lambda x: x.update(extra=True),
            lambda x: x.update(likelihood=[float("nan"), 0.8]),
        ]
        for i, mutate in enumerate(mutations):
            with self.subTest(i=i):
                value = self.fixture()
                got = copy.deepcopy(value)
                mutate(got)
                self.assertFalse(GATE.compare(value, got)["passed"])

    def test_original_tolerances(self):
        value = self.fixture()
        got = copy.deepcopy(value)
        got["state"]["post"][0][0] += 1e-14
        got["info"]["cut1_ms"] += 1e-10
        self.assertTrue(GATE.compare(value, got)["passed"])


if __name__ == "__main__":
    unittest.main()
