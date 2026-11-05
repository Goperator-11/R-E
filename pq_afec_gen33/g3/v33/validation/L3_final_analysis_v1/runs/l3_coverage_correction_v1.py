import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path


BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
path = RUNS / "L3_coverage.md"
backup = RUNS / "L3_coverage_before_tracking_correction.md"
out = RUNS / "L3_coverage_correction_v1.json"
assert not backup.exists() and not out.exists()
before = path.read_bytes()
text = before.decode("utf-8")
old_row = next(line for line in text.splitlines() if line.startswith("| A7-16 |"))
assert "처리함(TS 금지와 검증 범위)" in old_row
new_row = "| A7-16 | 다른 과제로 넘김(E8) | 카드의 TS 금지는 지켰지만 그것만으로 감사 제안의 처리가 끝난 것은 아니다. 검증자의 보조 수단 타당성·정상 구간 비용 단서를 유지한다. C1 재평가 억제 후보는 미채택이고 S·k 불확실성 탐색은 미구현이다. 이 범위 검토를 E8 카드에 추가하며 TS를 도입하지 않는다. |"
old_count = "처리함1행은 TS 금지와 해석 범위에 한정된다. 다른 과제로 넘김10행, 빈칸0이다. L3 전체 완료나 후보 채택으로 집계하지 않는다."
assert old_count in text
text = text.replace(old_row, new_row).replace(old_count, "처리함0행, 다른 과제로 넘김11행, 빈칸0이다. 카드의 금지 준수와 감사 제안의 처리를 구분한다. L3 전체 완료나 후보 채택으로 집계하지 않는다.")
with backup.open("xb") as stream:
    stream.write(before)
path.write_text(text, encoding="utf-8", newline="\n")
extra = BASE / "state/EXTRA_TASKS.md"
with extra.open("a", encoding="utf-8", newline="\n") as stream:
    stream.write("E8 추적 보충: A7-16의 C1 재평가 억제와 S·k 불확실성 탐색의 미완료 범위도 검토한다. TS 금지를 지킨 사실은 제안을 구현한 사실과 다르므로 L3 coverage를 처리함에서 E8 이관으로 정정했다. TS 금지는 유지한다.\n")
with (RUNS / "L3_extra_tasks_after_tracking_correction.md").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(extra.read_text(encoding="utf-8"))
receipt = {"coverage_path": str(path), "before_sha256": hashlib.sha256(before).hexdigest(),
    "after_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "backup_path": str(backup),
    "reason": "A7-16 source review: following TS prohibition alone does not complete the proposal; all11 L3 items retain followup scope",
    "supersedes_document_hash_in": "L3_final_disposition_v1.json", "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(receipt, ensure_ascii=False))
