import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))


def number(value):
    return "미확인" if value is None else f"{value:.6f}"


def main():
    findings_path, check_path = RUNS / "L3_findings_v1.json", RUNS / "L3_joint_artifact_check_v1.json"
    findings, check = read(findings_path), read(check_path)
    assert check["status"] == "pass" and check["error"] is None
    assert findings["provenance"]["check_sha256"] == sha(check_path)
    assert findings["provenance"]["report_sha256"] == sha(ROOT / "g3/v33/L3_benchmark_v1.json")
    groups = {(row["generation"], row["scenario"]): row for row in findings["groups"]}
    pairs = {(row["candidate"], row["baseline"], row["scenario"]): row for row in findings["comparisons"]}
    scenarios = sorted(sid for generation, sid in groups if generation == "l3_c1")
    assert len(scenarios) == 15 and len(groups) == 165 and len(pairs) == 210
    lines = ["# L3 전후 개발 평가", "", "동결한 독립 사건 세계에서 같은 seed31~50으로 비교했다. 기대 비용은 전체101행동에 같은 N131072·seed850001을 적용해 계산했다. 실제 네트워크 측정이나 확증 결과가 아니다.", "",
        "비용 차이는 후보에서 L1을 뺀 값이다. 조정 구간은 seed95% 구간과 공유 MC 오차를 함께 반영한다. 같은 문맥의 오라클 선택 오차는 짝차이에서 상쇄된다. 절대 후회에는 오라클 선택 불확실성이 남을 수 있다.", "",
        "| 시나리오 | 관측 | L1 기대 후회(ms/연결) | L3 기대 후회(ms/연결) | 짝차이(ms/연결) | 조정 구간(ms/연결) | 비열등 |",
        "|---|---|---:|---:|---:|---|---|"]
    for sid in scenarios:
        for mode in ("none", "c1"):
            before, after = groups["l1_" + mode, sid], groups["l3_" + mode, sid]
            pair = pairs["l3_" + mode, "l1_" + mode, sid]
            assert math.isclose(after["expected_regret_ms"] - before["expected_regret_ms"], pair["mean_ms"], rel_tol=1e-10, abs_tol=1e-10)
            lines.append(f"| {sid} | {mode} | {number(before['expected_regret_ms'])} | {number(after['expected_regret_ms'])} | {number(pair['mean_ms'])} | [{number(pair['adjusted_lower_ms'])}, {number(pair['adjusted_upper_ms'])}] | {pair['gate']} |")
    lines += ["", "| 비교 | 주 비교 | 셀 | 통과 | 실패 | 미확정 |", "|---|---|---:|---:|---:|---:|"]
    for name, value in findings["pair_summaries"].items():
        lines.append(f"| {name} | {'예' if value['primary'] else '아니오'} | {value['cells']} | {value['pass']} | {value['fail']} | {value['inconclusive']} |")
    lines += ["", "주 비교는 L3 none 대 L1 none, L3 c1 대 L1 c1, L3 c1 대 v31의45셀이다. guard·record·beta의 단계별 비교와 ideal은 진단이다. 단계별 진단 결과로 전체 후보를 교체하지 않는다.", "",
        "| C1 시나리오 | 전체 결정 | 감시 관측 | 경보 | 경보/1000결정 | seed95% 구간 | 행동 보정 | 공통 변화 |",
        "|---|---:|---:|---:|---:|---|---:|---:|"]
    for sid in scenarios:
        monitor = groups["l3_c1", sid]["monitor"]
        interval = monitor["all_decision_alarm_seed_summary"]
        lines.append(f"| {sid} | {monitor['connections']} | {monitor['monitored']} | {monitor['alarms']} | {number(interval['mean'])} | [{number(interval['lower'])}, {number(interval['upper'])}] | {monitor['action_model']} | {monitor['shared_change']} |")
    lines += ["", "B1 완료 기준의 경보 분모는 전체 결정 수다. 기존 observed의 유효 관측 분모 경보율과 섞지 않는다. B9의 새 연결마다 초기화되는 상태에서는 감시 관측이 없으며, 감시 관측 분모의 비율은 미정의다.", "",
        "| 사전 지정 조건 | 판정 |", "|---|---|"]
    for name, gate in findings["absolute_and_alarm_gates"].items():
        lines.append(f"| {name} | {gate['status']} |")
    for name, field in (("전체45셀 비열등", "primary_all_pass"), ("알려진q 주입 중앙15결정 이내", "known_q_injection_pass"), ("모든 채택 조건", "candidate_eligible_for_adoption")):
        lines.append(f"| {name} | {'충족' if findings[field] else '미충족'} |")
    lines += ["", "알려진q 시험의 감지 지연은250회 중 미감지를 무한대로 포함한 중앙값이다. 이 시험이 폐루프의 모형 오류와 실제 손실 변화를 식별한다는 뜻은 아니다.", "",
        f"원자료 요약: L3_findings_v1.json SHA256 {sha(findings_path)}.",
        f"독립 검사: L3_joint_artifact_check_v1.json SHA256 {sha(check_path)}.",
        f"표 생성기: l3_before_after_table_v1.py SHA256 {sha(__file__)}.",
        "전체210대조의 seed 구간·공유 MC 폭·절대 경계와 미확정 값은 L3_findings_v1.md 및 L3_bench_v1.md에 보존했다."]
    out = RUNS / "L3_bench.md"
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    print(json.dumps({"path": str(out), "sha256": sha(out), "paired_before_after_rows": 30, "comparison_families": 14}))


if __name__ == "__main__":
    main()
