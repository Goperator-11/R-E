import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(path, value):
    assert not path.exists()
    compile(value, str(path), "exec")
    path.write_text(value, encoding="utf-8", newline="\n")

helper = (RUNS / "j6_preflight_audit_v2.py").read_text(encoding="utf-8")
assert helper.count('"a_pre_n": len(selected), "a_pre_median": value,') == 1
helper = helper.replace('"a_pre_n": len(selected), "a_pre_median": value,', '"a_pre_n": len(selected), "a_pre_median": float(value),')
save(RUNS / "j6_preflight_audit_v3.py", helper)
checker = (RUNS / "j6_joint_artifact_check_v1.py").read_text(encoding="utf-8")
checker = checker.replace("j6_preflight_audit_v2.py", "j6_preflight_audit_v3.py")
checker = checker.replace(sha(RUNS / "j6_preflight_audit_v2.py"), sha(RUNS / "j6_preflight_audit_v3.py"))
save(RUNS / "j6_joint_artifact_check_v2.py", checker)
for source, dest in (("j6_checker_fixture_check_v1.py", "j6_checker_fixture_check_v2.py"),
                     ("j6_preflight_fixture_check_v1.py", "j6_preflight_fixture_check_v2.py")):
    value = (RUNS / source).read_text(encoding="utf-8")
    value = value.replace("j6_joint_artifact_check_v1.py", "j6_joint_artifact_check_v2.py")
    value = value.replace("J6_checker_fixture_check_v1.json", "J6_checker_fixture_check_v2.json")
    value = value.replace("J6_preflight_fixture_check_v1.json", "J6_preflight_fixture_check_v2.json")
    value = value.replace("J6_preflight_mutations_v1", "J6_preflight_mutations_v2")
    save(RUNS / dest, value)
note = "# J6 독립 검사기 중앙값 표현 정정\n\n첫 smoke 재생은 보조 Audit의 Python 숫자 동등성으로 통과했다. 최종 검사기의 JSON 정규화 동등성으로 재검사하자 홀수 표본 중앙값을 정수41로 만든 검사기가 정책의41.0과 다르다고 거부했다. 정책은 원래 계약대로 중앙값을 float, 예산을 정수로 저장했다. 검사기만 v3에서 중앙값 표현을 float로 맞췄다. v1·v2와 최초 실패 스크립트를 보존했다. 수집·정책·성능 문턱은 바꾸지 않았다.\n"
with (RUNS / "J6_preflight_checker_revision.md").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(note)
print(sha(RUNS / "j6_joint_artifact_check_v2.py"))
