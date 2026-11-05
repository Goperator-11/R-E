import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
import math
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
rows = [{"k": k, "m": m, "lead_choices": m+1, "ordered_subsets_per_lead": sum(math.perm(k+m, s) for s in range(k+m+1))} for k in range(1, 5) for m in range(5)]
value = {"action_settings": sum(row["lead_choices"] for row in rows), "arrival_order_and_erasure_cases": sum(row["lead_choices"]*row["ordered_subsets_per_lead"] for row in rows), "rows": rows, "formula": "sum over k=1..4,m=0..4 of (m+1)*sum over s=0..k+m of P(k+m,s)", "scope": "Exact prospective test inventory count only. Each datagram appears zero or one times. Duplicates, corruption, deadlines and resource limits require additional cases. No decoder tests or simulations executed.", "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
with (RUNS / "M1_reading_during_L5_v3.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
note = f"""# M1 순열·소거 검사의 규모

k=1..4, m=0..4, lead=0..m에서 원본·패리티 각각이0회 또는1회 도착하는 모든 순열과 소거 집합을 세면 {value['action_settings']}개 행동 설정, {value['arrival_order_and_erasure_cases']}개 사례다. n=k+m일 때 받은 s개를 고른 뒤 순서를 정하는 경우의 수는 P(n,s)이고 s=0..n을 합했다. k4·m4 한 lead 설정에는109601개 사례가 있다. 계산 스크립트와 정수 결과를 함께 남겼다.

이 수는 시험 실행 수가 아니다. 아직 디코더를 돌리지 않았다. 중복·손상·메타데이터 충돌·타이머와 도착의 동시 시각·TTL·버퍼 상한·작은 출력 버퍼는 이 목록과 별도 사례다. 구현할 때 각 원본·패리티를 구분한 사례 ID와 전체 예상 수를 먼저 고정하고, 조각 실행을 하더라도 누락·중복이 없는 집합을 확인해야 한다. 테스트가 느리다는 이유로 완료 기준의 모든 순서를 무작위 표본으로 바꾸지 않는다.
"""
with (RUNS / "M1_reading_during_L5_v3.md").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(note)
state_path = BASE / "state/LOOP_STATE.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
assert state["current"] == "L5" and state["tasks"]["M1"]["status"] == "todo"
state["tasks"]["M1"].setdefault("handoff_notes", []).append(str(RUNS / "M1_reading_during_L5_v3.md"))
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"action_settings": value["action_settings"], "prospective_cases": value["arrival_order_and_erasure_cases"], "tests_executed": 0}))
