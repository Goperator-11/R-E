import itertools
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from padfec import policy, quantum
from padfec3 import layout

S0_MLKEM = policy.S0_BASE_MLKEM
S0_X25519 = policy.S0_BASE_X25519
C_PKT = policy.C_PKT_POLICY_DEFAULT

P_GRID = (0.0, 0.001, 0.005, 0.02, 0.05, 0.1, 0.15, 0.3)
CERTS = (2955, 4032, 5956, 7194, 9000, 10908, 12000, 14622, 16000, 18336)
W_GRID = (1200, 1280, 1281, 1350)


def need_grid():
    out = set(range(1, 21))
    for cert in CERTS:
        out.add(layout.n_need(cert, s0_base=S0_MLKEM, c_pkt=C_PKT))
        out.add(layout.n_need(cert, s0_base=S0_X25519, c_pkt=C_PKT))
    return sorted(out)


def all_actions(k_max=layout.K_MAX, m_max=layout.M_MAX):
    for k in range(1, k_max + 1):
        for m in range(0, m_max + 1):
            for lead in range(0, m + 1):
                yield k, m, lead


def test_pattern_probabilities_sum_to_one():
    for k, m, lead in all_actions():
        for p in (0.0, 0.02, 0.15, 0.3):
            for u in (0.0, 2.0, 10.0):
                recs = list(layout.outcomes(k, m, lead, 1280, p, u))
                assert math.fsum(r["pr"] for r in recs) == pytest.approx(1.0, abs=1e-12)
                for r in recs:
                    if r["kind"] == "ok":
                        assert math.fsum(wg for wg, _c in r["branches"]) == pytest.approx(1.0, abs=1e-12)
                        assert all(wg > 0 for wg, _c in r["branches"])


def test_outcome_masses_partition():
    for k, m, lead in all_actions():
        for p in (0.0, 0.02, 0.15, 0.3):
            for u in (0.0, 2.0, 100.0):
                r = layout.evaluate(k, 1280, m, lead, p, 50.0, u, 10)
                assert r["p_success"] + r["p_fail"] == pytest.approx(1.0, abs=1e-12)
                assert r["p_one_rtt"] + r["p_two_rtt"] == pytest.approx(r["p_success"], abs=1e-12)
                split = r["p_fail_pto"] + r["p_fail_pto_sampled"] + r["p_fail_ack"]
                assert split == pytest.approx(r["p_fail"], abs=1e-12)
                assert r["e"] == pytest.approx(r["p_two_rtt"] + r["p_fail"], abs=1e-15)
                assert 0.0 <= r["e"] <= 1.0 + 1e-12


def test_legacy_layout_matches_gen2_flight_outcome():
    worst = {}
    count = 0
    for k in (1, 2, 3):
        for m in (0, 1, 2, 3):
            for w in W_GRID:
                for p in P_GRID:
                    for nn in need_grid():
                        g2 = policy.flight_outcome(k, m, w, p, 1.0, nn, trail_delay_ms=0.0)
                        for lead in (layout.LEGACY_LEAD, layout.legacy_lead(m)):
                            r = layout.evaluate(k, w, m, lead, p, 50.0, 0.0, nn, later="off")
                            pairs = (("p_fail", g2["p_fail"]),
                                     ("p_two_rtt", g2["p_two_rtt"]),
                                     ("n_rtt_expected", g2["n_rtt_expected"]),
                                     ("n_rtt_given_ok", g2["n_rtt_given_ok"]),
                                     ("p_fail_pto", g2["p_fail_pto"]),
                                     ("p_fail_pto_sampled", g2["p_fail_pto_sampled"]),
                                     ("p_fail_ack", g2["p_fail_ack"]))
                            for key, ref in pairs:
                                d = abs(r[key] - ref)
                                worst[key] = max(worst.get(key, 0.0), d)
                                assert d <= 1e-12, (k, m, w, p, nn, key, r[key], ref)
                            count += 1
    assert count == 3 * 4 * len(W_GRID) * len(P_GRID) * len(need_grid()) * 2


def test_legacy_success_cost_equals_gen2_rounds_times_rtt():
    for k in (1, 2, 3):
        for m in (0, 1, 2, 3):
            for p in (0.0, 0.02, 0.15):
                for nn in (5, 7, 10, 13, 15, 16):
                    g2 = policy.flight_outcome(k, m, 1280, p, 1.0, nn)
                    r = layout.evaluate(k, 1280, m, -1, p, 50.0, 0.0, nn, later="off")
                    assert r["n_rtt_expected"] * 50.0 == pytest.approx(g2["n_rtt_expected"] * 50.0, abs=1e-10)
                    if p == 0.0:
                        assert r["J"] == pytest.approx(g2["n_rtt_expected"] * 50.0, abs=1e-12)


def test_credit_never_exceeds_physically_arrived_bytes():
    checked = 0
    for k, m, lead in all_actions():
        for w in (1200, 1280, 1350):
            for u in (0.0, 2.0, 10.0, 100.0):
                for rec in layout.outcomes(k, m, lead, w, 0.1, u):
                    if rec["kind"] != "ok":
                        continue
                    assert rec["base_credit"] <= rec["phys_at_dec"]
                    for wgt, cred in rec["branches"]:
                        j = (cred - rec["base_credit"]) // layout.parity_bytes(w, k)
                        assert 0 <= j <= len(rec["after_sizes"])
                        assert cred <= rec["phys_at_dec"] + sum(rec["after_sizes"][:j])
                        assert cred <= rec["phys_bytes"]
                        checked += 1
    assert checked > 10000


def test_leading_datagrams_never_used_for_recovery():
    for k, m, lead in all_actions():
        for p in (0.02, 0.15, 0.3):
            base = layout.evaluate(k, 1280, m - lead, 0, p, 50.0, 0.0, 10)
            r = layout.evaluate(k, 1280, m, lead, p, 50.0, 0.0, 10)
            assert r["p_fail"] == pytest.approx(base["p_fail"], abs=1e-14)
            assert r["p_fail_pto"] == pytest.approx(base["p_fail_pto"], abs=1e-14)
            assert r["p_fail_pto_sampled"] == pytest.approx(base["p_fail_pto_sampled"], abs=1e-14)
            assert r["p_fail_ack"] == pytest.approx(base["p_fail_ack"], abs=1e-14)


def test_credit_only_failure_is_any_original_lost():
    for k in range(1, layout.K_MAX + 1):
        for lead in range(0, layout.M_MAX + 1):
            for p in (0.02, 0.15, 0.3):
                r = layout.evaluate(k, 1280, lead, lead, p, 50.0, 2.0, 10)
                assert r["p_fail"] == pytest.approx(1.0 - (1.0 - p) ** k, abs=1e-14)
                assert r["p_fail_pto"] == pytest.approx(p ** k, abs=1e-14)


def test_p_fail_monotone_in_p_and_trailing_count():
    for k, m, lead in all_actions():
        prev = -1.0
        for p in P_GRID:
            pf = layout.evaluate(k, 1280, m, lead, p, 50.0, 2.0, 10)["p_fail"]
            assert pf >= prev - 1e-15
            prev = pf
    for k in range(1, layout.K_MAX + 1):
        for p in (0.02, 0.15, 0.3):
            prev = 2.0
            for t in range(0, layout.M_MAX + 1):
                pf = layout.evaluate(k, 1280, t, 0, p, 50.0, 0.0, 10)["p_fail"]
                assert pf <= prev + 1e-15
                prev = pf


def test_cost_monotone_in_rtt_uplink_and_need():
    for k, m, lead in all_actions(k_max=3):
        for p in (0.0, 0.02, 0.15):
            prev = -1.0
            for rtt in (10.0, 50.0, 100.0, 200.0):
                J = layout.j3(k, 1280, m, lead, p, rtt, 2.0, 10)
                assert J >= prev - 1e-9
                prev = J
            prev = float("inf")
            for u in (1.0, 2.0, 5.0, 10.0, 20.0, 100.0, 0.0):
                J = layout.j3(k, 1280, m, lead, p, 50.0, u, 10)
                assert J <= prev + 1e-9
                prev = J
            prev = -1.0
            for nn in range(1, 22):
                J = layout.j3(k, 1280, m, lead, p, 50.0, 2.0, nn)
                assert J >= prev - 1e-9
                prev = J


def test_response_terms_add_exactly_on_two_rtt_mass():
    for k, m, lead in all_actions(k_max=3):
        for p in (0.0, 0.02, 0.15):
            for u in (0.0, 2.0, 10.0):
                off = layout.evaluate(k, 1280, m, lead, p, 50.0, u, 12, later="off")
                v3 = layout.evaluate(k, 1280, m, lead, p, 50.0, u, 12, later="v3")
                g2 = layout.evaluate(k, 1280, m, lead, p, 50.0, u, 12, later="g2")
                assert v3["J"] - off["J"] == pytest.approx(off["p_two_rtt"] * layout.tau(1280, u), abs=1e-9)
                extra = ((layout.tau(layout.parity_bytes(1280, 1), u) if m >= 2 else 0.0)
                         + (layout.G2_PARITY_DELAY_MS if m >= 1 else 0.0))
                assert g2["J"] - v3["J"] == pytest.approx(off["p_two_rtt"] * extra, abs=1e-9)
                assert v3["p_two_rtt"] == off["p_two_rtt"] == g2["p_two_rtt"]


def test_lossless_cost_is_deterministic():
    for k, m, lead in all_actions():
        for nn in (5, 7, 10, 13, 15, 16, 20):
            pre = layout.pre_decision_bytes(k, m, lead, 1280)
            r = layout.evaluate(k, 1280, m, lead, 0.0, 50.0, 2.0, nn)
            n = layout.rtt_count(pre, nn)
            want = layout.tau(pre, 2.0) + 50.0 * n + (layout.tau(1280, 2.0) if n == 2 else 0.0)
            assert r["J"] == pytest.approx(want, abs=1e-12)
            assert r["p_fail"] == 0.0
            r0 = layout.evaluate(k, 1280, m, lead, 0.0, 50.0, 0.0, nn, later="off")
            n0 = layout.rtt_count(layout.client_bytes(k, m, 1280), nn)
            assert r0["J"] == pytest.approx(50.0 * n0, abs=1e-12)


def test_measured_anchors_of_credit_count():
    nn = layout.n_need(16000, s0_base=S0_MLKEM, c_pkt=C_PKT)
    assert nn == 15
    assert layout.evaluate(2, 1280, 3, -1, 0.0, 50.0, 0.0, nn)["p_one_rtt"] == 1.0
    assert layout.evaluate(2, 1280, 2, -1, 0.0, 50.0, 0.0, nn)["p_one_rtt"] == 0.0
    assert layout.evaluate(2, 1280, 3, -1, 0.0, 50.0, 2.0, nn)["p_one_rtt"] == 0.0
    assert layout.evaluate(2, 1280, 4, 3, 0.0, 50.0, 2.0, nn)["p_one_rtt"] == 1.0
    assert layout.pre_decision_bytes(2, 3, -1, 1280) == 3891
    assert layout.pre_decision_bytes(2, 4, 3, 1280) == 6553
    assert layout.client_bytes(2, 4, 1280) == 7884


def test_send_order_and_validation():
    assert layout.send_order(2, 0, -1) == ["O", "O"]
    assert layout.send_order(2, 1, -1) == ["O", "O", "P"]
    assert layout.send_order(2, 3, -1) == ["L", "O", "O", "P", "P"]
    assert layout.send_order(2, 4, 3) == ["L", "L", "L", "O", "O", "P"]
    assert layout.send_order(1, 2, 2) == ["L", "L", "O"]
    assert [layout.legacy_lead(m) for m in range(5)] == [0, 0, 1, 1, 1]
    with pytest.raises(ValueError):
        layout.send_order(2, 2, 3)
    with pytest.raises(ValueError):
        layout.send_order(2, 5, 1)
    with pytest.raises(ValueError):
        layout.send_order(0, 1, 0)
    with pytest.raises(ValueError):
        layout.send_order(2, 2, -2)
    with pytest.raises(TypeError):
        layout.send_order(2, 2.0, 1)
    with pytest.raises(ValueError):
        layout.evaluate(2, 1280, 2, 1, 0.02, 50.0, 2.0, 10, later="g3")
    with pytest.raises(ValueError):
        layout.evaluate(2, 1280, 2, 1, -0.01, 50.0, 2.0, 10)
    with pytest.raises(ValueError):
        layout.evaluate(2, 1280, 2, 1, 1.5, 50.0, 2.0, 10)


def test_n_need_has_no_defaults():
    with pytest.raises(TypeError):
        layout.n_need(9000)
    with pytest.raises(TypeError):
        layout.n_need(9000, s0_base=S0_MLKEM)
    with pytest.raises(TypeError):
        layout.n_need(9000, s0_base=None, c_pkt=C_PKT)
    for cert in CERTS:
        assert layout.n_need(cert, s0_base=S0_MLKEM, c_pkt=C_PKT) == quantum.bin_needed(
            cert, None, s0_base=S0_MLKEM, c_pkt=C_PKT)


def test_exact_timing_puts_lost_datagrams_off_the_link():
    pz = layout.parity_bytes(1280, 2)
    recs = {r["pattern"]: r for r in layout.outcomes(2, 4, 3, 1280, 0.1, 2.0)}
    r = recs[(0, 1, 1, 1, 1, 1)]
    assert r["t_dec"] == pytest.approx(layout.tau(2 * pz + 2 * 1280, 2.0), abs=1e-12)
    assert r["base_credit"] == 2 * pz + 2 * 1280
    r = recs[(1, 1, 1, 0, 1, 1)]
    assert r["kind"] == "ok"
    assert r["t_dec"] == pytest.approx(layout.tau(4 * pz + 1280, 2.0), abs=1e-12)
    assert r["after_delays"] == []
    r = recs[(1, 1, 1, 1, 0, 0)]
    assert r["kind"] == "ptoS"
    r = recs[(0, 0, 0, 0, 1, 1)]
    assert r["kind"] == "ok"
    assert r["decision_index"] == 5
    r = recs[(0, 0, 0, 0, 1, 0)]
    assert r["kind"] == "ack"
    assert r["t_last_o"] == pytest.approx(layout.tau(1280, 2.0), abs=1e-12)
    r = recs[(1, 1, 1, 0, 0, 1)]
    assert r["kind"] == "pto"
