import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/J1_v1"
sys.path.insert(0, str(SNAPSHOT))
from padfec3 import layout, learn3


sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def kl(truth, alternative):
    assert math.isclose(math.fsum(truth), 1.0, abs_tol=1e-12)
    assert math.isclose(math.fsum(alternative), 1.0, abs_tol=1e-12)
    return math.fsum(p * math.log(p / q) for p, q in zip(truth, alternative) if p > 0)


def binary(q, epsilon):
    value = (1 - epsilon) * q + epsilon * (1 - q)
    return (1 - value, value)


def main():
    assert learn3.STATE_VERSION == 7 and learn3.EPS == .01 and learn3.CLASS_EPS == .001
    sources = [SNAPSHOT / "padfec3/layout.py", SNAPSHOT / "padfec3/learn3.py",
        RUNS.parent / "evidence/verify-A1/v14_kl.py"]
    hashes = {str(path): sha(path) for path in sources}
    ctx = {"k": 2, "W": 1280, "u": 2., "rtt": 50.7, "n_need": 15}
    rows = []
    for action in ((0, 0, 4), (0, 3, 1)):
        evaluated = [layout.evaluate(2, 1280, 4, action[1], p, 50.7, 2., 15) for p in (.15, .2)]
        if action == (0, 0, 4):
            for p, value in zip((.15, .2), evaluated):
                fail = 6 * p ** 5 * (1 - p) + p ** 6
                independent = (0., (1 - fail) * (1 - p * p), fail + (1 - fail) * p * p)
                assert all(math.isclose(a, b, rel_tol=0, abs_tol=1e-12) for a, b in zip(independent, value["class_probabilities"]))
            event = [v["class_probabilities"][2] for v in evaluated]
        else:
            event = [v["e"] for v in evaluated]
        old = [binary(q, .01) for q in event]
        old_kl = kl(*old)
        current = [tuple(learn3.class_likelihood(ctx, action, grade)[learn3.G.index(p)] for grade in range(3)) for p in (.15, .2)]
        for value, probabilities in zip(evaluated, current):
            expected = tuple((1 - .001) * q + .001 * (1 - q) / 2 for q in value["class_probabilities"])
            assert probabilities == expected
        current_kl = kl(*current)
        zero_log_ratio = math.log(old[0][0] / old[1][0])
        rows.append({"action": list(action), "old_event_probabilities": event,
            "old_binary_noisy_probabilities": old, "old_binary_kl_nats": old_kl,
            "old_binary_mean_log_odds_scale_observations": math.log(10) / old_kl,
            "old_binary_all_zero_scale_observations": math.log(10) / zero_log_ratio,
            "j1_three_class_noisy_probabilities": current, "j1_three_class_kl_nats": current_kl,
            "j1_three_class_mean_log_odds_scale_observations": math.log(10) / current_kl})
    assert round(rows[0]["old_binary_mean_log_odds_scale_observations"]) == 582
    assert round(rows[0]["old_binary_all_zero_scale_observations"]) == 121
    assert round(rows[1]["old_binary_mean_log_odds_scale_observations"]) == 86
    assert all(sha(path) == value for path, value in hashes.items())
    result = {"schema": "padfec.v33.j1_information_diagnostic/1", "rows": rows, "source_sha256": hashes,
        "script_sha256": sha(__file__), "true_p": .15, "alternative_p": .2,
        "scope": "Fixed action IID model likelihood diagnostic. log(10)/KL is a mean log-likelihood accumulation scale, not an expected stopping time or closed-loop adaptation guarantee. No W1 data selection or extra sampling."}
    with (RUNS / "J1_likelihood_information_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    lines = ["# J1 고정 행동 정보량", "", "참 p=0.15와 대안 p=0.20을 고정한 IID 모형 진단이다.", "",
        "| 행동 | 과거 1비트 KL nats/관측 | log(10)/KL 관측 척도 | 전부 y=0일 때 관측 척도 | J1 3등급 KL nats/관측 | log(10)/KL 관측 척도 |",
        "|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['action']} | {row['old_binary_kl_nats']:.6f} | {row['old_binary_mean_log_odds_scale_observations']:.3f} | {row['old_binary_all_zero_scale_observations']:.3f} | {row['j1_three_class_kl_nats']:.6f} | {row['j1_three_class_mean_log_odds_scale_observations']:.3f} |")
    lines += ["", "과거 검증의 EPS0.01 1비트 계산에서 반올림582·121·86을 재현했다. 현재 J1 3등급은 CLASS_EPS0.001로 다른 라벨에 절반씩 섞는 우도다. 서로 다른 관측 모형의 수치를 같은 것으로 쓰지 않는다.",
        "log(10)/KL은 평균 로그우도 누적량으로 정의한 관측 수 척도다. 경계에 처음 도달하는 시간의 기댓값이나 실제 사후분포 고착 해소 시간은 아니다. 적응적 행동 선택·hazard·도착 증거·GE·모형 오류는 이 계산에 없다. 50~120결정이면 고착이 풀린다는 주장을 뒷받침하지 않는다.",
        "(0,0,4)의 세 물리 확률은 첫 비행 실패 6p⁵(1-p)+p⁶와 둘째 비행 p²로 별도 계산해 동결 J1과 비교했다. 수집과 W1 성능 판정은 변경하지 않았다.", ""]
    with (RUNS / "J1_likelihood_information_v1.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
