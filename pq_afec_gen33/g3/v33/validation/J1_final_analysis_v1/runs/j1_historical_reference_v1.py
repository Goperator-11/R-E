import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import importlib.util
import itertools
import json
import math
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
EVIDENCE = ROOT / "g3/v33/evidence"
sys.path[:0] = [str(ROOT), str(EVIDENCE)]
from padfec3 import layout
import common

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

original = load("a0_decomposition", EVIDENCE / "03_j3_decomposition.py")
burst = load("a0_burst", EVIDENCE / "04_burst_model.py")
baseline = load("l1_layout", ROOT / "g3/v33/policy_snapshots/L1_v1/padfec3/layout.py")
old = read(EVIDENCE / "03_j3_decomposition.json")
context = common.EvidenceContext(SimpleNamespace(root=ROOT, journals=Path(r"C:\dev\pq_afec_gen31\experiments\state"), out=RUNS / "J1_unused_context_output.json"))
sources = {str(p): sha(p) for p in (Path(original.__file__), Path(burst.__file__), Path(common.__file__),
    Path(baseline.__file__), Path(layout.__file__), Path(layout.policy.__file__), Path(layout.quantum.__file__),
    EVIDENCE / "03_j3_decomposition.json")}
grouped = {}
for run_id in ("run1", "run2"):
    for unit, value, segment, row in common.rows(context.load(f"p31_{run_id}_S_bigcert_units.jsonl")):
        arm = segment["arm"]
        action = tuple(row.get("action") or ()) if arm == "g3auto" else ((0, 3, 1) if arm == "g3fixL3" else None)
        if action not in ((0, 3, 1), (0, 0, 4)):
            continue
        for key in ((run_id, arm, value["loss"], action), ("pooled_runs", arm, value["loss"], action),
                    ("pooled_runs", "pooled_auto_and_fixed", value["loss"], action)):
            grouped.setdefault(key, []).append(row)
old_groups = {(r["run"], r["arm"], r["loss_percent"], tuple(r["action"])): r for r in old["results"]}
assert set(grouped) == set(old_groups)
results = []
for key, rows in sorted(grouped.items(), key=str):
    run_id, arm, loss, action = key
    previous = original.summarize(baseline, arm, loss, action, rows)
    recorded = old_groups[key]
    for field in ("observed_mean_ms", "rows", "observed", "gap_components", "initial_datagrams"):
        assert previous[field] == recorded[field], (key, field)
    d, lead, trail = action
    after = layout.evaluate(2, 1280 + d, lead + trail, lead, loss / 100, 50.7, 2.0, 15)
    before = previous["model"]["layout_evaluate"]
    increment = after["J"] - before["J"]
    assert abs(increment - after["second_flight_tail_ms"]) < 1e-11
    assert abs(previous["model"]["sum_minus_layout_ms"]) < 1e-10
    observed = previous["observed_mean_ms"]
    results.append({"run": run_id, "arm": arm, "loss_percent": loss, "action": action, "rows": len(rows),
        "observed_mean_ms": observed, "model_before_ms": before["J"], "model_after_ms": after["J"],
        "residual_before_ms": observed - before["J"], "residual_after_ms": observed - after["J"],
        "model_tail_increment_ms": increment, "observed_tail_excess_ms": previous["gap_components"]["tail_excess_ms"],
        "classes_after": after["class_probabilities"], "observed_classes": previous["observed"]})
normalizations = []
for k in range(1, 5):
    for m in range(5):
        for lead in range(m + 1):
            for p in (0.0, .02, .15, .3):
                for length in (None, 3):
                    first = [0.0, 0.0, 0.0]
                    for record in baseline.outcomes(k, m, lead, 1280, .5, 2.0):
                        mass = burst.pattern_probability(record["pattern"], p, length)
                        if record["kind"] != "ok":
                            first[2] += mass
                        else:
                            for weight, credit in record["branches"]:
                                nr = baseline.rtt_count(credit, 15, baseline.preflight_bytes(k, 2.0))
                                first[nr - 1] += mass * weight
                    q = p * p if m > lead else p
                    grades = [first[0], first[1] * (1 - q), first[2] + first[1] * q]
                    assert abs(math.fsum(first) - 1) < 1e-12
                    assert abs(math.fsum(grades) - 1) < 1e-12 and min(grades) >= 0
                    normalizations.append({"k": k, "m": m, "lead": lead, "p": p, "burst_length": length,
                        "grade_sum": math.fsum(grades), "first_flight_fail": first[2]})
for item in context.inputs:
    assert next(x for x in old["inputs"] if x["path"] == item["path"])["sha256"] == item["sha256"]
    sources[item["path"]] = item["sha256"]
assert all(sha(path) == expected for path, expected in sources.items())
result = {"schema": "padfec.v33.j1_historical_reference/1", "status": "pass",
    "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
    "sources_sha256": sources, "script_sha256": sha(__file__), "historical_groups": results,
    "normalization_cases": normalizations, "scope": "Historical A0 observed decomposition exactly replayed on unchanged sealed input bytes; J1 model only. GE is algebraic first-flight reweighting with IID later-loss approximation, not GE physical validation. W0 comparison remains separate."}
with (RUNS / "J1_historical_reference_v1.json").open("x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")
rows = [r for r in results if r["run"] == "pooled_runs" and r["arm"] == "pooled_auto_and_fixed"]
lines = ["# J1 과거 관측과 비용식 대조", "", "A0와 같은 봉인 원자료를 읽어 관측 분해의 동일성을 확인했다. 값은 개발 모형 점검이다.", "",
    "| 손실% | 행동 | 연결 | 관측 평균 ms | 전 모형 ms | 후 모형 ms | 전 잔차 ms | 후 잔차 ms | 관측 초과 꼬리 ms | 모형 추가 ms |",
    "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
for r in rows:
    values = [r[k] for k in ("observed_mean_ms", "model_before_ms", "model_after_ms", "residual_before_ms", "residual_after_ms", "observed_tail_excess_ms", "model_tail_increment_ms")]
    lines.append(f"| {r['loss_percent']} | {r['action']} | {r['rows']} | " + " | ".join("미정의" if v is None else f"{v:.6f}" for v in values) + " |")
lines += ["", f"전체{len(results)}개 관측 그룹과 IID·GE 재가중{len(normalizations)}개 확률 합 검사를 통과했다.",
    "GE의 연속 later 손실 확률은 이번 IID 식으로 검증하지 않았다. 물리 GE 모형은 J5에서 다룬다. 관측 잔차에는 J2 처리 시간과 J3 실패 타이머 오차가 남는다.", ""]
with (RUNS / "J1_historical_reference_v1.md").open("x", encoding="utf-8") as stream:
    stream.write("\n".join(lines))
print(json.dumps({"status": "pass", "historical_groups": len(results), "normalization_cases": len(normalizations), "pooled_rows": rows}))
