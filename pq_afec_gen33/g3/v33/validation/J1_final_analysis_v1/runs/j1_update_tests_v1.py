import sys
sys.dont_write_bytecode = True
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")

def replace(name, old, new):
    path = ROOT / name
    value = path.read_text(encoding="utf-8")
    assert old in value, (name, old)
    path.write_text(value.replace(old, new), encoding="utf-8", newline="\n")

replace("tests/test_padfec3_arrivals.py", 'q = [ev["p_one_rtt"], ev["p_two_rtt"], ev["p_fail"]]', 'q = list(ev["class_probabilities"])')
replace("tests/test_padfec3_arrivals.py", 'data["v"] == 4', 'data["v"] == 7')
replace("tests/test_padfec3_arrivals.py", 'version_four', 'version_seven')
replace("tests/test_padfec3_arrivals.py", 'for version in (1, 2, 3):', 'for version in (1, 2, 3, 4, 5, 6):')
replace("tests/test_padfec3_dev_regressions.py", 'version_four', 'version_seven')
replace("tests/test_padfec3_dev_regressions.py", 'self.assertEqual(data["v"], 4)', 'self.assertEqual(data["v"], 7)')
replace("tests/test_padfec3_dev_regressions.py", 'for version in (1, 2, 3):', 'for version in (1, 2, 3, 4, 5, 6):')
replace("tests/test_padfec3_learn.py", 'self.assertEqual(d["v"], 4)', 'self.assertEqual(d["v"], 7)')
replace("tests/test_padfec3_learn.py", 'want = ev["p_fail"] if nominal2 else ev["e"]', 'want = ev["class_probabilities"][2] if nominal2 else ev["e"]')
replace("tests/test_v33_policy_worker.py", 'self.assertEqual(rows[0]["result"]["state_version"], 4)', 'self.assertEqual(rows[0]["result"]["state_version"], 7)')
replace("tests/test_v33_l3_candidate.py", 'test_active_l1_rejects_l3_candidate_state', 'test_active_policy_rejects_l3_candidate_state')
replace("tests/test_v33_l3_candidate.py", 'assert learn3.STATE_VERSION == 4', 'assert learn3.STATE_VERSION != 6')
replace("tests/test_padfec3_layout.py", 'off["p_two_rtt"] * layout.tau(1280, u), abs=1e-9)', 'off["p_two_rtt"] * layout.tau(1280, u) + v3["second_flight_tail_ms"], abs=1e-9)')
replace("tests/test_padfec3_layout.py", 'off["p_two_rtt"] * extra, abs=1e-9)', 'off["p_two_rtt"] * extra - v3["second_flight_tail_ms"], abs=1e-9)')
replace("tests/test_padfec3_layout.py", 'resp = layout.response_term(m, w, u, "v3")\n    J', 'resp = layout.response_term(m, w, u, "v3")\n    q2 = p * p if m > lead else p\n    resp += q2 * 3.0 * (rtt + (lead * (w + 39 + 6 * k) + w) * 8.0 / (u * 1000) if u > 0 else rtt)\n    J')
print("J1 test expectations updated")
