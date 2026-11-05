import math

import pytest

from padfec3 import layout, learn3


@pytest.mark.parametrize("p", [0.0, .02, .15, .3, 1.0])
@pytest.mark.parametrize("m,lead", [(0, 0), (1, 0), (4, 0), (4, 3), (4, 4)])
def test_second_loss_does_not_change_first_flight_retry_mass(p, m, lead):
    before = layout.evaluate(2, 1280, m, lead, p, 50.7, 2.0, 15, "off")
    after = layout.evaluate(2, 1280, m, lead, p, 50.7, 2.0, 15)
    for key in ("p_one_rtt", "p_two_rtt", "p_fail", "round_mult", "e",
                "p_success", "n_rtt_expected", "n_rtt_given_ok"):
        assert after[key] == before[key]
    assert math.fsum(after["class_probabilities"]) == pytest.approx(1.0, abs=1e-12)
    assert all(0 <= q <= 1 + 1e-12 for q in after["class_probabilities"])
    if p in (0.0, 1.0):
        assert after["second_flight_tail_ms"] == 0


@pytest.mark.parametrize("p", [.02, .15, .3])
def test_one_original_one_xor_has_closed_form_classes(p):
    result = layout.evaluate(1, 1280, 1, 0, p, 50.0, 2.0, 100)
    assert result["class_probabilities"] == pytest.approx(
        (0, (1 - p * p) ** 2, 2 * p * p - p ** 4), abs=1e-12)
    assert result["p_fail"] == pytest.approx(p * p, abs=1e-12)


@pytest.mark.parametrize("lead,q,delay", [(0, .0225, 167.46), (3, .0225, 215.376), (4, .15, 231.348)])
def test_sample_rtt_includes_only_bytes_through_first_original(lead, q, delay):
    result = layout.evaluate(2, 1280, 4, lead, .15, 50.7, 2.0, 15)
    assert result["q_second_flight_loss"] == q
    assert result["second_flight_pto_ms"] == pytest.approx(delay, abs=1e-12)
    assert layout.evaluate(2, 1280, 4, lead, .15, 50.7, 0.0, 15)["second_flight_pto_ms"] == pytest.approx(152.1, abs=1e-12)


@pytest.mark.parametrize("lead,before,increment", [
    (0, 116.87247150767497, 3.7663478641757804),
    (3, 104.44632568837389, 1.7563362749887501)])
def test_corrected_audit_cost_reference(lead, before, increment):
    result = layout.evaluate(2, 1280, 4, lead, .15, 50.7, 2.0, 15)
    assert result["J"] == pytest.approx(before + increment, abs=1e-11)
    assert result["second_flight_tail_ms"] == pytest.approx(increment, abs=1e-12)


def test_corrected_audit_crossover_uses_sampled_rtt():
    lo, hi = .1, .35
    for _ in range(60):
        p = (lo + hi) / 2
        a = layout.j3(2, 1280, 4, 3, p, 50.7, 2.0, 15)
        b = layout.j3(2, 1280, 4, 0, p, 50.7, 2.0, 15)
        if a >= b:
            hi = p
        else:
            lo = p
    assert (lo + hi) / 2 == pytest.approx(.21479062755790823, abs=1e-13)


@pytest.mark.parametrize("later", ["off", "g2"])
def test_legacy_comparison_modes_keep_their_existing_tail_contract(later):
    result = layout.evaluate(2, 1280, 4, 0, .15, 50.7, 2.0, 15, later)
    assert result["second_flight_tail_ms"] == result["p_second_flight_tail"] == 0
    assert result["class_probabilities"] == (result["p_one_rtt"], result["p_two_rtt"], result["p_fail"])


def test_nominal_two_round_likelihood_contains_later_loss():
    ctx = {"k": 2, "W": 1280, "u": 2.0, "rtt": 50.7, "n_need": 15}
    action = (0, 0, 4)
    g = learn3.G.index(.15)
    late = learn3.class_probabilities(ctx, action, g)[2]
    assert late > .0225
    assert late == learn3.event_prob(ctx, action, g)
    assert learn3.class_likelihood(ctx, action, 2, epsilon=0)[g] == late


def test_model_world_catalogue_samples_tail_events_separately():
    from experiments import adaptation_benchmark as model_world
    result = model_world.cost_catalogue(2, 1280, (0, 0, 4), .15, 50.7, 2.0, 15)
    mass = math.fsum(atom["probability"] for atom in result["atoms"] if atom.get("second_flight_tail"))
    assert mass == pytest.approx((1 - (6 * .15 ** 5 * .85 + .15 ** 6)) * .0225, abs=1e-12)
    pair = result["by_pattern"][(1, 1, 1, 1, 1, 1)]
    assert len(pair) == 2
    assert pair[1]["synthetic_cost_ms"] - pair[0]["synthetic_cost_ms"] == pytest.approx(167.46, abs=1e-12)
