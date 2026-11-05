import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
ROOT = Path(r"C:\dev\pq_afec_gen33")
RE = Path(r"C:\dev\R-E")
commit = "73aa4203c52eebac1eb1ce073b0b32f149768a44"
paths = ["pq_afec/experiments/quicbed/qamp.go", "pq_afec/experiments/quicbed/qamp_decoder_lifecycle_test.go"]
git = ["git", "-C", str(RE)]
diff = subprocess.check_output(git + ["show", "--format=", commit, "--"] + paths)
diff_path = RUNS / "M1_reading_during_L5_S4_decoder.diff"
with diff_path.open("xb") as stream:
    stream.write(diff)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
note = """# M1과 S4의 복호기 변경 경계

L5 반복24의 읽기 검토다. R-E 커밋73aa420의 qamp.go와 복호기 수명 시험 차이를 읽고 runs에 보존했다. R-E 작업 트리와 gen33 소스는 고치지 않았다.

S4가 옮길 수정은 패리티만 도착해도 만료를 실행하는 것, 만료된 비행의 heldBytes를 전체 보류량에서 빼는 것, 작은 수신 버퍼로 복원본을 전달할 때 실제 copy 길이만 스택에 계상하는 것, 같은 비행의 상충 메타데이터를 거부하는 것이다. 현재 gen33 qamp.go에는 sameFecFlight가 없고, pending에서는 copy 이전에 원본 길이를 계상한다. 이 범위는 M1 보류 버퍼의 바이트 상한·만료·인계에도 직접 닿는다.

원래 gen-2 sameFecFlight는 flight·k·m·symLen·crcs·lens를 비교한다. v3에는 ver·lead가 더 있으므로 의미대로 이식할 때 둘도 계약에 포함되는지 확인해야 한다. 감사 카드의 순서를 그대로 따라 M1이 먼저 실행되더라도, 이미 알려진 수명·메타데이터 결함 위에 새 보류 상태를 무검증으로 얹지 않는다. 필요한 공통 수정은 범위를 명시해 시험하고 S4의 완료로 자동 표시하지 않는다. 이후 S4에서는 원래9개 파일의 나머지 정책·채널·캐시 수정과 관문을 모두 확인해야 한다.

이 기록은 새 구현의 설계 참고다. 실제 재정렬·보류 타이머·상한·복호 순열 시험은 아직 하지 않았다. 보존한 diff의 시험 수나 과거 커밋 메시지의 통과 수는 이번 gen33 실행 결과가 아니다.
"""
value = {"scope": "Read-only comparison of S4 decoder changes needed by future M1; no port or tests executed", "commit": commit, "blob_sha256": {p: hashlib.sha256(subprocess.check_output(git + ["show", commit + ":" + p])).hexdigest() for p in paths}, "diff_path": str(diff_path), "diff_sha256": sha(diff_path), "current_qamp_sha256": sha(ROOT / "experiments/quicbed/qamp.go"), "script_sha256": sha(__file__)}
for name, text in (("M1_reading_during_L5_v2.json", json.dumps(value, ensure_ascii=False, indent=2) + "\n"), ("M1_reading_during_L5_v2.md", note)):
    with (RUNS / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
print(json.dumps({"commit": commit, "read_blobs": len(paths), "diff_sha256": value["diff_sha256"]}))
