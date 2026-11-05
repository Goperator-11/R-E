from padfec import policy, quantum
from padfec3 import decide3


def test_parity_geometry_and_receive_limit():
    assert policy.PARITY_OVERHEAD_BASE == 46
    assert policy.PARITY_OVERHEAD_PER_K == 6
    assert policy.PARITY_DATAGRAM_MAX == decide3.UDP_MAX == 1452
    for k, cap in ((1, 1400), (2, 1394), (3, 1388), (4, 1382)):
        assert policy.parity_datagram_bytes(cap, k) == 1452
        assert policy.parity_datagram_bytes(cap + 1, k) == 1453


def test_all_generated_candidates_fit_the_receiver():
    for k in range(1, 5):
        for w in (1200, 1280, 1350, 1382, 1388, 1394, 1400, 1452):
            for cert in (1000, 4032, 9000, 11000, 12000, 16000, 30000):
                size = cert + 1472 + quantum.bin_index(k * w) * policy.C_PKT_POLICY_DEFAULT
                candidates = decide3.candidates3(k, w, size, policy.C_PKT_POLICY_DEFAULT)
                assert candidates
                for candidate in candidates:
                    if candidate["m"]:
                        assert candidate["W_eff"] + 46 + 6 * k <= 1452


def test_c12000_oversize_l5_action_is_not_an_eligible_candidate():
    candidates = decide3.candidates3(2, 1280, 13934, policy.C_PKT_POLICY_DEFAULT)
    assert (130, 2, 2) not in {c["action"] for c in candidates}
