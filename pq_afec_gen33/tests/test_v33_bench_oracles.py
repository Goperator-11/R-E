import copy

import pytest

from experiments.v33 import bench_oracles, oracle


def fixture(mode="build", structural=False):
    protocol = {"oracle":{"stage_sizes":[4, 8], "validation_samples":8,
                          "min_elimination_samples":4, "m_max":0,
                          "original_max_bytes":1281}}
    context = {"context":{"k":2, "w":1280, "p":0 if structural else .02,
                          "rtt_ms":50, "uplink_mbps":2,
                          "cert_bytes":2955 if structural else 9000},
               "world_params":{}, "mixture":[]}
    job = {"context_id":"synthetic", "job_id":"synthetic"}
    family = 1 if mode == "actions" else None
    if mode == "actions":
        job.update(action=[1,0,0], reference_action=[0,0,0], job_id="synthetic_1_0_0")
    expected, spec, params, mixture, universe = bench_oracles._expected_result_contract(protocol, context, mode, family)
    result = {"schema":oracle.SCHEMA, "status":"complete", "context_id":job["context_id"],
              "job_id":job["job_id"], "source_hashes":oracle._source_hashes(),
              "approximate":not structural, "validation_samples":0 if structural else 8,
              **expected}
    if mode == "build":
        result.update(model_kind="independent_event_world", chosen_action=[0,0,0])
    else:
        result.update(action=job["action"], reference_action=job["reference_action"],
                      validation_seed=spec["validation_seed"], n=0 if structural else 8,
                      evaluation_family_size=1)
    if structural:
        result.update(method="structural_zero_loss_certificate" if mode == "build" else "structural_zero_loss_pair",
                      certificate=oracle._certificate(mixture, params, oracle._source_hashes(), spec),
                      uncertainty_resolved=True)
        if mode == "build":
            result.update(confidence=None, stage_results=[], oracle_gap_upper_ms=0.0,
                          selection_gap_upper_ms=0.0)
    else:
        result.update(method="paired_stage_screening_then_independent_validation" if mode == "build" else "independent_paired_validation",
                      confidence=spec["confidence"])
        if mode == "build":
            history = [{"stage_index":i, "new_independent_connections":n,
                        "seed":oracle._derive_seed(spec["selection_seed"], f"selection_stage:{i}"),
                        "reference_action":[0,0,0], "empirical_choice":[0,0,0],
                        "before":len(universe), "after":len(universe), "eliminated":[]}
                       for i,n in enumerate(spec["stage_sizes"])]
            result.update(validation_seed=spec["validation_seed"], validation_changed_choice=False,
                          selection_stage_samples_are_fresh_blocks=True, history=history,
                          stage_results=copy.deepcopy(history), validation_candidate_count=len(universe),
                          validation=[{"action":list(a), "n":8} for a in universe],
                          total_world_evaluations=len(universe)*(sum(spec["stage_sizes"])+8))
        else:
            result["evaluation_seed_must_not_have_selected_either_action"] = True
    return result, {"protocol":protocol, "context_spec":context, "job":job,
                    "mode":mode, "evaluation_family_size":family}


@pytest.mark.parametrize("mode", ["build", "actions"])
@pytest.mark.parametrize("structural", [False, True])
def test_complete_contract_accepts_mc_and_structural_zero_samples(mode, structural):
    result, arguments = fixture(mode, structural)
    bench_oracles.validate_oracle_result(result, **arguments)


@pytest.mark.parametrize("key", ["context", "mixture", "world_params_sha256", "spec",
                                "universe_count", "universe_sha256", "max_parity",
                                "source_hashes", "validation_samples", "validation_seed"])
@pytest.mark.parametrize("mutation", ["missing", "changed"])
def test_complete_result_rejects_missing_or_changed_identity(key, mutation):
    result, arguments = fixture()
    if mutation == "missing":
        result.pop(key)
    else:
        result[key] = "changed"
    with pytest.raises(ValueError):
        bench_oracles.validate_oracle_result(result, **arguments)


@pytest.mark.parametrize("key,value", [("n",7), ("n",0), ("evaluation_family_size",2),
                                       ("validation_samples",7), ("validation_seed",840001)])
def test_action_evaluation_rejects_wrong_sample_seed_or_family(key, value):
    result, arguments = fixture("actions")
    result[key] = value
    with pytest.raises(ValueError):
        bench_oracles.validate_oracle_result(result, **arguments)


def test_validation_rows_and_selection_history_cannot_omit_samples():
    result, arguments = fixture()
    result["validation"][0]["n"] = 7
    with pytest.raises(ValueError, match="validation row n"):
        bench_oracles.validate_oracle_result(result, **arguments)
    result, arguments = fixture()
    result["history"][0]["new_independent_connections"] = 3
    result["stage_results"] = copy.deepcopy(result["history"])
    with pytest.raises(ValueError, match="new_independent_connections"):
        bench_oracles.validate_oracle_result(result, **arguments)


def test_survivors_must_reach_validation_and_keep_the_chosen_action():
    result, arguments = fixture()
    result["validation"].pop()
    result["validation_candidate_count"] = 1
    with pytest.raises(ValueError, match="validation actions"):
        bench_oracles.validate_oracle_result(result, **arguments)
    result, arguments = fixture()
    result["chosen_action"] = [1,0,0]
    with pytest.raises(ValueError, match="chosen_action"):
        bench_oracles.validate_oracle_result(result, **arguments)


@pytest.mark.parametrize("mode", ["build", "actions"])
def test_structural_zero_samples_require_the_pinned_certificate(mode):
    result, arguments = fixture(mode, True)
    result["certificate"]["proof"] = "unverified"
    with pytest.raises(ValueError, match="certificate"):
        bench_oracles.validate_oracle_result(result, **arguments)
    result, arguments = fixture(mode, True)
    result["validation_samples"] = 8
    with pytest.raises(ValueError, match="validation_samples"):
        bench_oracles.validate_oracle_result(result, **arguments)


def test_action_metadata_records_full_contract_without_overwriting_conflicts():
    result, arguments = fixture("actions", True)
    for key in ("spec", "universe_count", "universe_sha256", "max_parity", "validation_samples", "evaluation_family_size"):
        result.pop(key)
    bench_oracles._complete_action_metadata(result, arguments["protocol"], arguments["context_spec"], 1)
    bench_oracles.validate_oracle_result(result, **arguments)
    result["spec"]["validation_samples"] = 4
    with pytest.raises(ValueError, match="spec"):
        bench_oracles._complete_action_metadata(result, arguments["protocol"], arguments["context_spec"], 1)


def manifest_fixture(mode="build"):
    _, arguments = fixture(mode)
    return {"schema":"padfec.v33.oracle_jobs/1", "mode":mode, "protocol_sha256":"frozen",
            "source_sha256":{name:bench_oracles.bench.file_hash(bench_oracles.Path(bench_oracles.__file__).with_name(name))
                             for name in bench_oracles.MANIFEST_SOURCES},
            "jobs":[arguments["job"]], "evaluation_family_size":1 if mode == "actions" else None,
            "oracle_digests":{"synthetic":"reference"} if mode == "actions" else {}}


@pytest.mark.parametrize("mode", ["build", "actions"])
def test_manifest_has_explicit_mode_sources_jobs_and_family(mode):
    manifest = manifest_fixture(mode)
    bench_oracles.validate_oracle_manifest(manifest, protocol_hash="frozen", mode=mode)
    manifest["mode"] = "actions" if mode == "build" else "build"
    with pytest.raises(ValueError, match="mode"):
        bench_oracles.validate_oracle_manifest(manifest, protocol_hash="frozen", mode=mode)


@pytest.mark.parametrize("mutation", ["missing", "extra", "changed", "empty"])
def test_manifest_rejects_incomplete_or_changed_source_hashes(mutation):
    manifest = manifest_fixture()
    if mutation == "missing":
        manifest["source_sha256"].pop("worldsim.py")
    elif mutation == "extra":
        manifest["source_sha256"]["unexpected.py"] = "untrusted"
    elif mutation == "changed":
        manifest["source_sha256"]["oracle.py"] = "changed"
    else:
        manifest["source_sha256"] = {}
    with pytest.raises(ValueError, match="source"):
        bench_oracles.validate_oracle_manifest(manifest, protocol_hash="frozen", mode="build")
