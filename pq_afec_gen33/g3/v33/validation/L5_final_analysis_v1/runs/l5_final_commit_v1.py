import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L5_final_analysis_v1"
BASE = "91432c35c122dd83bc946b2d53e68c96bd6fa14b"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    manifest_path = DEST / "manifest.json"
    assert sha(manifest_path) == args.manifest_sha256
    manifest = read(manifest_path)
    assert manifest["file_count"] == len(manifest["entries"])
    check_path = RUNS / "L5_joint_artifact_check_v3.json"
    check = read(check_path)
    findings = read(RUNS / "L5_findings_v1.json")
    assert check["status"] == "pass" and check["error"] is None
    assert findings["checker_sha256"] == sha(check_path)
    adopted = findings["candidate_adopted"]
    assert adopted is False
    labels = ("L5_core_check_02", "L5_collector_check_01", "L5_final_checks_01") if adopted else ("L5_revert_check_02",)
    for label in labels:
        tests = read(RUNS / (label + ".json"))
        assert tests["exit_code"] == 0 and tests["unchanged"]
        assert all(sha(path) == expected for path, expected in tests["source_sha256"].items())
    if not adopted:
        assert read(RUNS / "L5_revert_candidate_v1.json")["active_policy_exactly_matches_l1"] is True
    doc = ROOT / "docs/L5_disposition.md"
    assert not doc.exists()
    with doc.open("xb") as stream:
        stream.write((RUNS / "L5_disposition.md").read_bytes())
    git = ["git", "-C", str(ROOT)]
    paths = ["padfec/quantum.py", "padfec3/decide3.py", "padfec3/learn3.py", "padfec3/layout.py",
        "tests/test_padfec3_arrivals.py", "tests/test_padfec3_dev_regressions.py", "tests/test_padfec3_learn.py",
        "tests/test_v33_policy_worker.py", "tests/test_padfec3_followup.py", "tests/test_v33_l3_candidate.py", "docs/L5_disposition.md",
        "g3/v33/L5_benchmark_v1.json", "g3/v33/L5_benchmark_v1.json.published.json"]
    if not adopted:
        paths += ["tests/test_v33_l5_candidate.py", "experiments/v33/candidate_tests/l5_test_padfec3_server_size.py", "experiments/v33/candidate_tests/l5_test_v33_server_response_observer.py"]
    subprocess.run(git + ["add", "--"] + paths, check=True, capture_output=True)
    subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
    staged = subprocess.check_output(git + ["diff", "--cached", "--name-only", "--no-renames", "-z"]).decode("utf-8").split("\0")
    allowed = set(paths) | {"padfec3/server_size.py", "tests/test_padfec3_server_size.py", "tests/test_v33_server_response_observer.py"}
    assert all(not name or name in allowed or name.startswith("g3/v33/validation/L5_final_analysis_v1/") for name in staged), staged
    entries = [(DEST / row["stored"], row["stored_sha256"]) for row in manifest["entries"]]
    entries.append((manifest_path, sha(manifest_path)))
    entries += [(ROOT / name, sha(ROOT / name)) for name in paths if (ROOT / name).is_file()]
    request = "".join(":" + path.relative_to(ROOT).as_posix() + "\n" for path, _ in entries).encode("utf-8")
    data = subprocess.run(git + ["cat-file", "--batch"], input=request, capture_output=True, check=True).stdout
    position = 0
    for path, expected in entries:
        end = data.index(b"\n", position)
        fields = data[position:end].split()
        assert len(fields) == 3 and fields[1] == b"blob", (path, fields)
        size = int(fields[2])
        assert hashlib.sha256(data[end + 1:end + 1 + size]).hexdigest() == expected == sha(path), path
        position = end + 2 + size
    assert position == len(data)
    for directory in ("afec", "padfec", "padfec3"):
        for path in (ROOT / directory).glob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            expected = (ROOT / "g3/v33/policy_snapshots/L5_v1" / relative).read_bytes() if adopted else subprocess.check_output(git + ["show", BASE + ":" + relative])
            assert path.read_bytes() == subprocess.check_output(git + ["show", ":" + relative]) == expected, relative
    title = "L5: 관측 사전 ACK와 여유를 개발 정책의 신용 경계에 반영" if adopted else "L5: 전체 평가 후보를 보존하고 활성 L1 복구"
    message = f"{title}\n\n전체3000실행·150그룹·210대조와 독립{check['checks']}검사를 보존했다.\n원래30채택셀 판정은 {findings['primary_counts']}이다.\nc12000 none·C1은 약24.9 ms 악화했고 각 팔26980/27000회 패리티 크기 초과를 진단했다.\n복구351시험·548하위검사가 통과했다.\n두 새 산출법의 역사 관문은 N·tail·완료 패킷목록 부족으로 미완료다.\n증거{manifest['file_count']}파일과 압축 추적1500개의 원형 위치·SHA를 보존했다.\n실제 wire·Go·서버 재전송 식별과 잔여 감사 범위는 별도로 남겼다.\n"
    message_path = RUNS / "L5_final_commit_message.txt"
    with message_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(message)
    result = subprocess.run(git + ["commit", "-F", str(message_path)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
    receipt = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
        "commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(),
        "bundle_manifest_sha256": sha(manifest_path), "verified_index_blobs": len(entries), "git_status": "clean",
        "candidate_adopted": adopted, "script_sha256": sha(__file__)}
    with (RUNS / "L5_final_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps(receipt))

if __name__ == "__main__":
    main()
