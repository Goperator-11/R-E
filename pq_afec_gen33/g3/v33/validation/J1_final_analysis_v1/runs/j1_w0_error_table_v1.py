import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sys.path.insert(0, str(ROOT))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

before = load("l1_error_layout", ROOT / "g3/v33/policy_snapshots/L1_v1/padfec3/layout.py")
after = load("j1_error_layout", ROOT / "g3/v33/policy_snapshots/J1_v1/padfec3/layout.py")
source = ROOT / "g3/v33/validation/W0/W0_world_validation.json"
document = json.loads(source.read_text(encoding="utf-8"))
assert document["schema"] == "padfec.v33.world_validation_results/1"
sources = {str(p): sha(p) for p in (source, Path(before.__file__), Path(after.__file__), Path(after.policy.__file__), Path(after.quantum.__file__))}
rows = []
z = statistics.NormalDist().inv_cdf(.975)
for case in document["calibration"]:
    c = case["context"]
    delta, lead, trail = case["action"]
    args = (c["k"], c["w"] + delta, lead + trail, lead, c["p"], c["rtt_ms"], c["uplink_mbps"], c["n_need"])
    old, new = before.evaluate(*args), after.evaluate(*args)
    sampled = case["sampled"]
    half = z * sampled["stderr_hct_ms"]
    rows.append({"id": case["id"], "world_context": c, "action": case["action"], "n": sampled["n"],
        "world_mean_ms": sampled["mean_hct_ms"], "world_pointwise_95_normal_ci_ms": [sampled["mean_hct_ms"] - half, sampled["mean_hct_ms"] + half],
        "model_before_ms": old["J"], "model_after_ms": new["J"],
        "world_minus_model_before_ms": sampled["mean_hct_ms"] - old["J"],
        "world_minus_model_after_ms": sampled["mean_hct_ms"] - new["J"],
        "model_probability_assumption": "IID even when world_context.loss_model is ge", "tail_increment_ms": new["second_flight_tail_ms"]})
assert len(rows) == 7
result = {"schema": "padfec.v33.j1_w0_error_table/1", "status": "complete", "sources_sha256": sources,
    "script_sha256": sha(__file__), "rows": rows,
    "world_source_sha256_at_original_run": {p: h for p, h in document["source_sha256"].items() if "worldsim" in p or "worldparams" in p},
    "scope": "Seven complete W0 default-world calibration cases reused without resampling or parameter changes. Normal intervals are pointwise descriptions of stored world means, not simultaneous adoption gates. Model uses true specified RTT/need and IID probabilities, separate from noisy policy inputs and physical observations."}
with (RUNS / "J1_w0_error_table_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write("\n")
lines = ["# J1과 W0 기본 세계의 오차", "", "W0에서 완료한7조건을 모두 사용했다. 조건마다100000표본이며 세계를 다시 실행하거나 매개변수를 고치지 않았다. RTT와 n_need는 지정된 참 입력이다.", "",
    "| 조건 | 행동 | 세계 평균 ms | 점별95% 구간 ms | 전 모형 ms | 후 모형 ms | 전 잔차 ms | 후 잔차 ms |",
    "|---|---|---:|---|---:|---:|---:|---:|"]
for r in rows:
    low, high = r["world_pointwise_95_normal_ci_ms"]
    lines.append(f"| {r['id']} | {r['action']} | {r['world_mean_ms']:.6f} | [{low:.6f}, {high:.6f}] | {r['model_before_ms']:.6f} | {r['model_after_ms']:.6f} | {r['world_minus_model_before_ms']:.6f} | {r['world_minus_model_after_ms']:.6f} |")
lines += ["", "p18의 세계는 GE이며 두 정책 비용식은 IID다. 이 행의 잔차는 GE 보정의 효과가 아니다. RTT200에는 세계의 첫 표본 전 PTO가 포함된다. 처리 시간·첫 비행 실패 타이머·재전송 모양도 잔차에 남는다.",
    "구간은 저장된 세계 평균의 표준오차에 정규 임계값을 곱한 점별 기술 구간이다. W1의 동시 MC 오차 보정 및 seed 짝비교 관문과 구분한다.", ""]
with (RUNS / "J1_w0_error_table_v1.md").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("\n".join(lines))
assert all(sha(p) == h for p, h in sources.items())
print(json.dumps({"status": "complete", "cases": len(rows), "rows": [{k:r[k] for k in ("id", "world_minus_model_before_ms", "world_minus_model_after_ms")} for r in rows]}))
