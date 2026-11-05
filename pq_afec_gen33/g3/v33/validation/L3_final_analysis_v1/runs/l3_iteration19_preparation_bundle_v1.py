import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L3_iteration19_preparation_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
assert not DEST.exists()
names = ["iter018_last.json", "iter018_payload.json", "iter019_preflight.py", "iter019_preflight_initial.json",
    "iter019_preflight.json", "iter019_sources.txt", "iter019_recent_journal.txt", "iter019_start.py",
    "l3_prepare_final_bundle_v2.py", "l3_final_bundle_v2.py", "l3_revert_candidate_v1.py", "l3_candidate_wrapper_template.py",
    "l3_before_after_table_v1.py", "L3_joint_progress_03.json", "L3_joint_progress_04.json", "L3_joint_progress_05.json",
    "L3_joint_progress_06.json", "l3_iteration19_preparation_bundle_v1.py"]
entries = []
for name in names:
    source, target = RUNS / name, DEST / name
    text = source.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    if source.suffix == ".py":
        ast.parse(text, filename=str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    entries.append({"source": str(source), "stored": name, "source_sha256": sha(source), "stored_sha256": sha(target)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "scope": "Iteration19 preflight and post-validation disposition tooling. Revert, candidate wrapper installation, final table and bundle have not executed."}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path, expected in [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest, sha(manifest))]:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == expected
message = RUNS / "L3_iteration19_preparation_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L3): 반복19 사전 점검과 판정 뒤 보존 준비\n\n연결11감사·검증 단서와 상태 파일을 다시 읽었다.\n고정101행동 중52개 결과 파일, 실패기록0을 확인했으며 성능값은 읽지 않았다.\n최종 전후표·반복19 보존·미채택일 때의 조건부 복구 도구를 준비했다. 실행은 전체 보고와 독립 검사 뒤다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
out = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "manifest_sha256": sha(manifest), "files": len(entries), "index_blobs_verified": len(entries) + 1}
with (RUNS / "L3_iteration19_preparation_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(out, stream, indent=2)
    stream.write("\n")
print(json.dumps(out))
