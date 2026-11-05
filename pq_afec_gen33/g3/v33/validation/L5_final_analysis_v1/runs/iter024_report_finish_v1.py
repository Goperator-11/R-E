import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import re

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
state = read(BASE / "state/LOOP_STATE.json")
assert state["iterations"] == 24 and state["current"] is None and state["tasks"]["L5"]["status"] == "blocked"
last = read(RUNS / "iter024_last.json")
assert last["task_id"] == "L5" and last["next_task"] == "J7" and not last["measurement_running"]
coverage = read(RUNS / "iter024_coverage_status.json")
findings = read(RUNS / "L5_findings_v1.json")
assert findings["candidate_adopted"] is False
path = RUNS / "MORNING_REPORT.md"
before = path.read_bytes()
text = before.decode("utf-8")
overview = f"최근 완료 반복: 24. 활성 정책은 L1 상태4다. L5는 주 비교 {findings['primary_counts']}, c12000 none·C1 약24.9 ms 악화와 역사 관문 입력 부족으로 미채택이며 E11에 후속을 등록했다. 감사194항목의 기록 집계는 {coverage['counts']}다. 이 수는 추적 기록 범위이며 수정 완료 건수가 아니다. 현재 측정·CPU 계산은 없고 다음 과제는 J7이다. [L5 판정](C:/dev/codex_handoff/v33/runs/L5_disposition.md), [전후 표](C:/dev/codex_handoff/v33/runs/L5_bench.md)."
if re.search(r"(?m)^최근 완료 반복:.*$", text):
    text = re.sub(r"(?m)^최근 완료 반복:.*$", lambda _: overview, text, count=1)
else:
    assert "\n## 진행\n" in text
    text = text.replace("\n## 진행\n", "\n" + overview + "\n\n## 진행\n", 1)
addition = "D18의 기본값은 역사 입력이 없으면 세계 성능으로 대체 채택하지 않는 것이다. 반복24에서는 c12000의 none·C1 비열등 실패도 확인했으며 이 규칙을 적용해 L5를 미채택으로 기록하고 L1을 복구했다. 새 N·tail을 만들지 않았으며 E11은 J7·T4 뒤에 수행한다."
section = re.search(r"(## 도현님 결정이 필요한 것\n)(.*?)(?=\n## |\Z)", text, re.S)
assert section and addition not in section.group(2)
text = text[:section.end(2)] + "\n" + addition + "\n" + text[section.end(2):]
with (RUNS / "iter024_report_finish_before.md").open("xb") as stream:
    stream.write(before)
path.write_text(text, encoding="utf-8", newline="\n")
receipt = {"before_sha256": hashlib.sha256(before).hexdigest(), "after_sha256": sha(path), "scope": "Updated latest iteration overview and D18 outcome only; retained historical numbers and failure entries", "script_sha256": sha(__file__)}
with (RUNS / "iter024_report_finish.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(json.dumps(receipt))
