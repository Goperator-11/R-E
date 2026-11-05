import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L3_joint_plan_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = ["git", "-C", str(ROOT)]
manifest = DEST / "manifest.json"
value = json.loads(manifest.read_text(encoding="utf-8"))
for row in value["entries"]:
    assert sha(row["source"]) == row["source_sha256"]
    assert sha(DEST / row["stored"]) == row["stored_sha256"]
dirty = subprocess.check_output(git + ["status", "--porcelain", "--untracked-files=all"], text=True).splitlines()
assert dirty and all(line.startswith("?? " + DEST.relative_to(ROOT).as_posix() + "/") for line in dirty), dirty
failure = {"stage": "l3_joint_plan_bundle_v1.py", "reason": "Clean-tree assertion was placed after creating the new untracked bundle", "outputs_changed": False,
    "resolution": "Verify every original and stored SHA, require only this new bundle to be untracked, then stage and verify Git blobs"}
with (RUNS / "L3_joint_plan_bundle_v1_failure.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(failure, stream, indent=2)
    stream.write("\n")
for name in ("l3_joint_plan_commit_v2.py", "L3_joint_plan_bundle_v1_failure.json"):
    source, target = RUNS / name, DEST / name
    with target.open("xb") as stream:
        stream.write(source.read_bytes())
    value["entries"].append({"source": str(source), "stored": name, "source_sha256": sha(source), "stored_sha256": sha(target)})
manifest.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path, expected in [(DEST / row["stored"], row["stored_sha256"]) for row in value["entries"]] + [(manifest, sha(manifest))]:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == expected
message = RUNS / "L3_joint_plan_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L3): 전체101행동 평가 계획과 독립 검사 고정\n\n원자료3300실행 검증397.51초 정상 종료. N131072와 seed850001 유지.\n합성165그룹·210대조 독립 집계56999검사와 오류 주입7건 거부 통과.\n보존기 최초호출은 새 폴더를 만든 뒤 clean 검사를 해 중단됐고, 원본·저장 SHA와 변경 범위를 대조해 보존을 마쳤다.\n전체 후보 성능과 채택은 아직 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
out = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "manifest_sha256": sha(manifest), "files": len(value["entries"]), "index_blobs_verified": len(value["entries"]) + 1}
with (RUNS / "L3_joint_plan_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(out, stream, indent=2)
    stream.write("\n")
print(json.dumps(out))
