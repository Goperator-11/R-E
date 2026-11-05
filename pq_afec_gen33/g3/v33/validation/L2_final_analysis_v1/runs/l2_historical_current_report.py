import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
current_path = RUNS / "L2_historical_current_v2.json"
old_path = RUNS / "L2_historical_grade_precheck.json"
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
current, old = read(current_path), read(old_path)
assert current["status"] == old["status"] == "pass"
assert current["inputs"] == old["inputs"]
assert current["results"] == json.loads(json.dumps(old["results"]).replace("l1_", "l2_"))
lines = ["# L2 과거 라벨 재생", "", "현재 L2 코드와 A0가 사용한 같은6777행을 대조했다. 분류 함수와 보조 검증 함수 다섯 개의 AST가 L1 보존본과 같고, layout SHA도 같다.", "",
         "| run | 손실층 % | 행 수 | 새 1-RTT | 새 2-RTT | 새 지연·실패 | 기존 누락→새 2-RTT | 기존 비정상→새 정상 | 기존 정상→새 비정상 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
total, missed, false = 0, 0, 0
for run, values in current["results"].items():
    for loss, value in sorted(values.items(), key=lambda pair: float(pair[0])):
        n = value["original_A0_reproduction"]["rows"]
        counts = value["l2_grade_counts"]
        missing = value["old_missed_y0_to_l2_grade"]
        assert set(missing) <= {"1"}
        assert value["old_non_one_now_l2_one"] == 0 and value["old_one_now_l2_non_one"] == 0
        lines.append(f"| {run} | {loss} | {n} | {counts.get('0', 0)} | {counts.get('1', 0)} | {counts.get('2', 0)} | {missing.get('1', 0)} | 0 | 0 |")
        total += n
        missed += missing.get("1", 0)
        if float(loss) == 2:
            false += value["old_one_now_l2_non_one"]
assert total == 6777 and missed == 141 and false == 0
lines += ["", "A0의 기존 시간 경계에서 비정상인 행이 새 정상 등급으로 들어간 경우는0건이다. 기존 y=0이 놓쳤던141행은 모두 새2-RTT 등급이다. 2%층에서 기존 정상 행을 새 비정상 등급으로 바꾼 경우도0건이다.", "",
          "선택된 자료에는 실패·경계 누락 행이 없으며, EPS 학습이나 전체 정책을 재생한 결과가 아니다. 원래 시간 경계도 물리적 왕복 수의 독립 정답은 아니다. 저장된 policy_rtt_ms와 action(0,3,1), k2, W1280B, 업링크2Mbps, c_proc 여유3ms를 고정했다.", "",
          "첫 v1 호출은 A0의 예전 decide3.py SHA를 상속해 입력 확인 단계에서 중단됐다. v2는 이미 고정한 L2 decide3.py의 SHA를 명시했고, 원자료와 A0 재현 검사·분류 산술은 유지했다. 두 소스와 실패 기록을 보존했다.", "",
          f"현재 결과 SHA256: `{sha(current_path)}`.", f"비교한 L1 준비 결과 SHA256: `{sha(old_path)}`.", ""]
out = RUNS / "L2_historical_current_v2.md"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("\n".join(lines))
print(json.dumps({"rows": total, "old_missed_now_two": missed, "false_new_non_one_at_2_percent": false, "markdown_sha256": sha(out)}))
