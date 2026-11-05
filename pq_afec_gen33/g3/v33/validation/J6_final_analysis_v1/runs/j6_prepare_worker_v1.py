import sys
sys.dont_write_bytecode = True
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
path = ROOT / "experiments/v33/policy_worker.py"
text = path.read_text(encoding="utf-8")
text = text.replace('APPROVED_EXTRA = {"first_flight_evidence": "arrivals"}', 'APPROVED_EXTRA = {"first_flight_evidence": "arrivals", "preflight": "preflight_observation"}')
old = '        arguments = {APPROVED_EXTRA[key]: first_flight_evidence(value) for key, value in optional.items()}'
new = '''        arguments = {}
        for key, value in optional.items():
            if key == "first_flight_evidence":
                arguments[APPROVED_EXTRA[key]] = first_flight_evidence(value)
            else:
                self.learn.preflight.normalize(value, request.get("srv_bytes"))
                arguments[APPROVED_EXTRA[key]] = value'''
assert text.count(old) == 1
text = text.replace(old, new)
old = '"S_hat": self.learn.s_hat(state), "k_hat": self.learn.k_hat(state),'
new = '"S_hat": self.learn.s_hat(state), "S_scope": getattr(state, "S_scope", "legacy_unclassified"), "apre_history_count": len(getattr(state, "apre_hist", [])), "k_hat": self.learn.k_hat(state),'
assert text.count(old) == 1
text = text.replace(old, new)
with (ROOT / "experiments/v33/policy_worker_j6.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(text)
print("created isolated J6 worker")
