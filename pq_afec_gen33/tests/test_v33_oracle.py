import ast
import copy
from pathlib import Path

import pytest

from experiments.v33 import oracle
from experiments.v33.worldsim import World


def small_spec(**overrides):
    result = {"stage_sizes": [4, 8], "validation_samples": 8,
              "min_elimination_samples": 4, "max_parity": 0,
              "chunk_size": 2, "structural_certificates": False}
    result.update(overrides)
    return result


def small_context(**overrides):
    result = {"k": 1, "w": 1451, "p": 0.1, "rtt_ms": 50.0,
              "uplink_mbps": 2.0, "cert_bytes": 9000}
    result.update(overrides)
    return result


def test_integer_universe_is_independent_and_retains_truncated_parity():
    k2 = oracle.action_universe({"k": 2, "w": 1280, "cert_bytes": 16000})
    k1 = oracle.action_universe({"k": 1, "w": 1280, "cert_bytes": 4032})
    assert len(k2) == 2161
    assert len(k1) == 2245
    assert (122, 0, 1) in k2
    assert (141, 1, 0) in k2
    assert (142, 1, 0) not in k2
    assert (172, 0, 0) in k2
    assert len(k2) == len(set(k2))
    tree = ast.parse(Path(oracle.__file__).read_text(encoding="utf-8"))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name and name.startswith(("padfec", "afec")) for name in imports)
    assert len(oracle.action_universe({"k": 2, "w": 1280}, spec={"m_max": 0})) == 173
    assert len(oracle.action_universe({"k": 2, "w": 1280}, spec={"m_max": 0, "original_max_bytes": 1280})) == 1
    assert (122, 0, 1) not in oracle.action_universe({"k": 2, "w": 1280}, spec={"wire_max_bytes": 1452})
    with pytest.raises(ValueError, match="disagree"):
        oracle.action_universe({"k": 2}, spec={"m_max": 4, "max_parity": 3})


@pytest.mark.parametrize("uplink", [0, 2])
def test_b3_structural_certificate_uses_originals_only(uplink):
    context = {"k": 2, "w": 1280, "cert_bytes": 2955, "p": 0,
               "s2c_loss": 0, "rtt_ms": 50, "uplink_mbps": uplink}
    report = oracle.build_oracle(context)
    assert report["status"] == "complete"
    assert report["method"] == "structural_zero_loss_certificate"
    assert report["chosen_action"] == [0, 0, 0]
    assert report["selection_gap_upper_ms"] == 0
    assert report["certificate"]["server_first_flight_bytes"] == 4595
    gap = oracle.evaluate_action(context, [1, 0, 0], [0, 0, 0])
    assert gap["approximate"] is False
    assert gap["mean_gap_ms"] == pytest.approx(0.008 if uplink else 0)


def test_b4_one_byte_crosses_granular_boundary():
    context = {"k": 1, "w": 1280, "cert_bytes": 4032, "p": 0,
               "s2c_loss": 0, "rtt_ms": 50, "uplink_mbps": 0}
    report = oracle.build_oracle(context)
    assert report["chosen_action"] == [1, 0, 0]
    assert report["certificate"]["server_first_flight_bytes"] == 4583
    gap = oracle.evaluate_action(context, [0, 0, 0], [1, 0, 0])
    assert gap["mean_gap_ms"] == pytest.approx(50)
    assert gap["gap_se_ms"] == 0
    assert gap["n"] == 0


def test_certificate_fails_closed_when_world_settings_change():
    spec = oracle._spec({})
    context = {"k": 2, "cert_bytes": 2955, "p": 0, "rtt_ms": 50, "uplink_mbps": 2}
    mixture = oracle._Mixture(context, spec)
    assert oracle._certificate(mixture, World().params, oracle._source_hashes(), spec) is not None
    altered = World({"c_proc_ms": 3}).params
    assert oracle._certificate(mixture, altered, oracle._source_hashes(), spec) is None
    sources = oracle._source_hashes()
    sources["worldsim.py"] = "changed"
    assert oracle._certificate(mixture, World().params, sources, spec) is None


def test_build_resume_matches_uninterrupted_result(tmp_path):
    checkpoint = tmp_path / "oracle.json"
    spec = small_spec(checkpoint_path=str(checkpoint), max_evaluations=1)
    partial = oracle.build_oracle(small_context(), spec=spec)
    assert partial["status"] == "partial"
    assert partial["chosen_action"] is None
    assert checkpoint.is_file()
    spec.pop("max_evaluations")
    resumed = oracle.build_oracle(small_context(), spec=spec)
    fresh_spec = small_spec()
    fresh = oracle.build_oracle(small_context(), spec=fresh_spec)
    assert resumed["status"] == "complete"
    assert resumed["chosen_action"] == fresh["chosen_action"]
    assert resumed["validation"] == fresh["validation"]
    assert resumed["stage_results"] == fresh["stage_results"]
    assert resumed["total_world_evaluations"] == fresh["total_world_evaluations"]


def test_evaluation_resume_and_identity_protection(tmp_path):
    checkpoint = tmp_path / "pair.json"
    spec = small_spec(checkpoint_path=str(checkpoint), max_evaluations=1)
    partial = oracle.evaluate_action(small_context(), [1, 0, 0], [0, 0, 0], spec=spec)
    assert partial["status"] == "partial"
    spec.pop("max_evaluations")
    resumed = oracle.evaluate_action(small_context(), [1, 0, 0], [0, 0, 0], spec=spec)
    fresh = oracle.evaluate_action(small_context(), [1, 0, 0], [0, 0, 0], spec=small_spec())
    assert resumed == fresh
    with pytest.raises(ValueError, match="identity mismatch"):
        oracle.evaluate_action(small_context(p=0.2), [1, 0, 0], [0, 0, 0], spec=spec)


def test_zero_observed_variance_never_removes_distinct_action():
    context = small_context(p=0, uplink_mbps=0)
    result = oracle.build_oracle(context, spec=small_spec())
    assert result["validation_candidate_count"] == 2
    assert result["zero_variance_unresolved_actions"]
    assert result["selection_gap_upper_ms"] is None
    assert result["uncertainty_resolved"] is False
    gap = oracle.evaluate_action(context, [1, 0, 0], [0, 0, 0], spec=small_spec())
    assert gap["uncertainty_resolved"] is False
    assert gap["gap_half_width_ms"] is None
    assert gap["gap_ci_ms"] is None


def test_zero_variance_candidate_cannot_supply_screening_upper_bound(monkeypatch):
    real_world = World

    class RareCostWorld:
        def __init__(self, params=None, profile="default", seed=0):
            real = real_world(params)
            self.params = real.params
            self.params_sha256 = real.params_sha256
            self.seed = seed

        def sample(self, context, action, connection=0):
            if action.delta == 0:
                cost = 100.0
            elif action.delta == 1:
                cost = 300.0 if self.seed == 850001 and connection == 0 else 90.0
            else:
                cost = 95.0 + (0.25 if connection % 2 else -0.25)
            return {"hct": cost, "ok": True, "server_counted_uplink_bytes": 100,
                    "client_total_uplink_bytes": 120}

    monkeypatch.setattr(oracle, "World", RareCostWorld)
    report = oracle.build_oracle(small_context(w=1450),
                                 spec=small_spec(stage_sizes=[1024], min_elimination_samples=1024))
    stage = report["stage_results"][0]
    assert stage["before"] == 3
    assert stage["after"] == 2
    assert stage["upper_bound_candidate_count"] == 2
    assert stage["zero_variance_upper_bounds_ignored"] == 1
    assert [row["action"] for row in stage["eliminated"]] == [[0, 0, 0]]
    assert report["chosen_action"] == [1, 0, 0]
    assert report["validation_candidate_count"] == 2
    assert report["selection_gap_upper_ms"] > 0
    assert report["validation_changed_choice"] is False


def test_validation_does_not_reselect_action(monkeypatch):
    real_world = World

    class DeliberatelyReversedWorld:
        def __init__(self, params=None, profile="default", seed=0):
            real = real_world(params)
            self.params = real.params
            self.params_sha256 = real.params_sha256
            self.seed = seed

        def sample(self, context, action, connection=0):
            if self.seed == 850001:
                cost = 20 if action.delta == 0 else 10 + connection % 2
            else:
                cost = 10 if action.delta == 0 else 20 + connection % 2
            return {"hct": cost, "ok": True, "server_counted_uplink_bytes": 100,
                    "client_total_uplink_bytes": 120}

    monkeypatch.setattr(oracle, "World", DeliberatelyReversedWorld)
    report = oracle.build_oracle(small_context(), spec=small_spec(min_elimination_samples=1024))
    assert report["chosen_action"] == [0, 0, 0]
    assert report["validation_changed_choice"] is False
    assert report["selection_gap_upper_ms"] > 9


def test_mixture_choice_is_shared_and_is_not_observed_before_action():
    spec = oracle._spec({"mixture": [{"weight": 0.65, "context": {"cert_bytes": 2955}},
                                    {"weight": 0.35, "context": {"cert_bytes": 16000}}]})
    mixture = oracle._Mixture({"k": 2}, spec)
    first = [mixture.at(850001, n).cert_bytes for n in range(50)]
    second = [mixture.at(850001, n).cert_bytes for n in range(50)]
    assert first == second
    assert set(first) == {2955, 16000}
    assert oracle._certificate(mixture, World().params, oracle._source_hashes(), spec) is None


def test_selection_and_validation_seed_reuse_is_rejected():
    with pytest.raises(ValueError, match="must differ"):
        oracle.build_oracle(small_context(), spec=small_spec(selection_seed=1, validation_seed=1))


def test_persistent_ge_requires_a_different_stateful_oracle():
    with pytest.raises(ValueError, match="persistent GE"):
        oracle.build_oracle(small_context(), {"preserve_ge_across_connections": True}, small_spec())
