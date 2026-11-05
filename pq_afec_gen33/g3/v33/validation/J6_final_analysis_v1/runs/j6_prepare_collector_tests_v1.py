import sys
sys.dont_write_bytecode = True
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
text = (ROOT / "tests/test_v33_learning_j1.py").read_text(encoding="utf-8")
text = text.replace("bench_learning_j1", "bench_learning_j6").replace('"state_version": 7', '"state_version": 8').replace("state_version=7", "state_version=8").replace("tail_variant", "budget_variant")
text = text.replace('["first_flight_evidence"]', '["first_flight_evidence", "preflight"]')
text = text.replace('patch.object(learning.bench, "PolicyWorker", FakeWorker)', 'patch.object(learning, "PolicyWorker", FakeWorker)')
text = text.replace('def test_none_disables_trace_and_feature_disabled_feedback_is_zero', 'def test_none_collects_preflight_trace_and_feature_disabled_feedback_is_zero')
text = text.replace('all(not value[2] for value in FakeWorld.calls)', 'all(value[2] for value in FakeWorld.calls)')
text = text.replace('"secret_world_truth": .88}', '''"secret_world_truth": .88,
                "model_kind": "independent_event_world", "trace": [
                    {"event": "client_receive", "time_ms": 1, "kind": "ack", "size": 41},
                    {"event": "client_receive", "time_ms": 2, "kind": "data", "size": 1280},
                    {"event": "client_receive", "time_ms": 3, "kind": "data", "size": 1679}]}''')
helper = '''
class PreservedDirectory:
    def __init__(self):
        base = Path(r"C:\\dev\\codex_handoff\\v33\\runs\\J6_test_fixtures")
        base.mkdir(parents=True, exist_ok=True)
        self.name = tempfile.mkdtemp(dir=base)

    def __enter__(self):
        return self.name

    def __exit__(self, *args):
        return False

    def cleanup(self):
        pass


'''
text = text.replace('class FakeWorker:', helper + 'class FakeWorker:')
text = text.replace('tempfile.TemporaryDirectory()', 'PreservedDirectory()')
text = text.replace('(out / "none/B1/seed00031.json").unlink()', '(out / "none/B1/seed00031.json").rename(out / "none/B1/seed00031.saved")')
text = text.replace('finished.unlink()', 'finished.rename(finished.with_suffix(".saved"))')
with (ROOT / "tests/test_v33_learning_j6.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(text)
print("created preserved J6 collector fixtures")
