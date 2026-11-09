import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/check_docs.py"
SPEC = importlib.util.spec_from_file_location("document_checks", SCRIPT)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def write(root, relative, text="내용\n"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def errors(root, text, name="docs/example.md"):
    return CHECK.check_file(root, write(root, name, text))


def fixed_table(root):
    write(root, "docs/fixed.md")
    return write(root, "docs/재현 절차.md", "## 9. 고정 문서\n\n"
                 "| 파일 | 누가 읽나 | 무엇이 깨지나 | 고쳐도 되는가 |\n"
                 "|---|---|---|---|\n"
                 "| `docs/fixed.md` | 검증기 | 해시 | 아니오 |\n"
                 "| `../archive/g3/SEAL_stage.json` | 보호 검사 | 봉인 | 로컬 보존 |\n")


@pytest.mark.parametrize("term", CHECK.TRANSLATIONS)
def test_rejects_translated_terms(tmp_path, term):
    assert any("translated term" in error for error in errors(tmp_path, term))


@pytest.mark.parametrize("text", ["문장\u2014문장", "문장\u2013문장", "완료 \U0001F680", "시험 1792 통과", "Go PASS 231"])
def test_rejects_style_and_obsolete_counts(tmp_path, text):
    assert errors(tmp_path, text)


def test_old_number_does_not_match_other_numbers(tmp_path):
    assert errors(tmp_path, "0.1792 17920 11792 1792.5 PASS 2310") == []
    assert errors(tmp_path, "시험 수는 1792.")


@pytest.mark.parametrize("location", ["C:/local/file", r"C:\local\file", "/mnt/c/local", "codex_handoff", "claude_brain", "AppData", "볼트"])
def test_external_location_requires_preservation_label(tmp_path, location):
    assert errors(tmp_path, location)
    assert errors(tmp_path, location + " (로컬 보존)") == []


def test_relative_links_inline_paths_and_line_numbers(tmp_path):
    write(tmp_path, "docs/target.md")
    write(tmp_path, "tools/runner.py", "pass\n")
    text = "[문서](target.md#절) `tools/runner.py:3` `python tools/runner.py`\n[참조]: target.md\n[웹](https://example.com/x)"
    assert errors(tmp_path, text) == []
    assert any("missing path" in error for error in errors(tmp_path, "[없음](missing.md)"))
    assert any("missing path" in error for error in errors(tmp_path, "`tools/missing.py`"))


def test_reference_paths_with_spaces_and_escaped_pipes(tmp_path):
    write(tmp_path, "docs/한글 문서.md")
    assert errors(tmp_path, "[문서](<한글 문서.md>) `한글 문서.md`") == []
    assert CHECK.cells(r"| `a\|b` | c |") == [r"`a\|b`", "c"]


def test_parent_and_export_excluded_paths_need_preservation(tmp_path):
    write(tmp_path, "g3/v33/validation/local.json", "{}")
    for target in ["../../outside.md", "g3/v33/validation/local.json"]:
        assert errors(tmp_path, f"`{target}`")
        assert errors(tmp_path, f"`{target}` (로컬 보존)") == []


def test_claim_table_exception_does_not_cover_body_or_other_documents(tmp_path):
    table = "| 금지 주장 | 이유 |\n|---|---|\n| 예측이 맞는다 | 범위를 벗어남 |\n"
    assert errors(tmp_path, table, "docs/CLAIMS.md") == []
    assert errors(tmp_path, table, "docs/동결 세대 문서 정정표.md") == []
    assert any("forbidden claim" in error for error in errors(tmp_path, table))
    assert any("forbidden claim" in error for error in errors(tmp_path, table + "\n예측이 맞는다\n", "docs/CLAIMS.md"))


def test_claim_negation_is_only_on_the_same_line(tmp_path):
    assert errors(tmp_path, "실측으로 개선 확인이라고 쓰지 않는다.") == []
    assert errors(tmp_path, "실측으로 개선 확인\n이 표현은 쓰지 않는다.")
    assert errors(tmp_path, "PTO 12.0% 대 10.4%, z=0.79로 기각")
    assert errors(tmp_path, "유의차가 없어 가설을 기각하였다.")
    assert errors(tmp_path, "같은 parity 바이트가 항상 credit과 복구를 함께 산다.")


def test_all_modes_enforce_existing_fixed_table(tmp_path, monkeypatch, capsys):
    fixed_table(tmp_path)
    write(tmp_path, "docs/example.md")
    def fake_git(root, *args):
        return subprocess.CompletedProcess(args, 0, "docs/fixed.md\n" if args[0] == "diff" else "", "")
    monkeypatch.setattr(CHECK, "git", fake_git)
    assert CHECK.main(["--root", str(tmp_path), "--file", "docs/example.md"]) == 1
    assert "fixed document differs from baseline" in capsys.readouterr().out


def test_ms23_and_ms20_qualified_historical_statements_pass(tmp_path):
    ms23 = ("이 연구는 v3.3.1-dev를 실제 QUIC 테스트베드에서 측정하지 않았다. "
            "이 판의 근거는 Python·Go 비트 일치 관문, 기능 시험, 결과 일부를 본 뒤의 개발용 세계 시뮬레이션뿐이며 성능 근거로 쓰지 않는다. "
            "실측 수치(S_bigcert +28.0/+28.9 ms, S_rtt200 +12.4/+10.3 ms)는 봉인 v3.1의 값이고 v3.3.1-dev로 옮겨 쓰지 않는다. "
            "조건은 quic-go v0.61.0 테스트베드 한 곳, 합성 인증서, 클라이언트에서 서버 방향 손실만, initial congestion window 32 packet, 정책에 참 uplink를 알려 준 설정이다. "
            "같은 바이트 padding 대 parity 비교(X1)는 하지 않았으므로 parity의 고유 몫은 직접 측정되지 않았고, 0단계 FEC 몫(2% 6.89 ms, 15% 41.04 ms)에는 datagram 하나를 더 보낸 효과가 섞여 있다. "
            "PTO 비율 재측정(X9)은 하지 않았으므로 12.0%, 10.4%, z=0.79는 분모가 확인되지 않은 옛 값으로만 언급하고 가설 기각의 근거로 쓰지 않는다.")
    ms20 = ("quic-go v0.61.0 테스트베드, RTT 50 ms, 손실 5%(c2s만 / 양방향)에서 x25519와 X25519MLKEM768의 PTO 사건 비율 차이는 d %p [L, U]였다(연결 6,100개씩, development). "
            "유의차가 없어도 가설 기각으로 쓰지 않는다. 옛 12.0%, 10.4%, z=0.79는 분모가 확인되지 않아 인용하지 않는다.")
    assert errors(tmp_path, ms23 + "\n" + ms20) == []


def test_contextual_claims_require_their_qualifier(tmp_path):
    for unqualified, qualified in [
        ("재방문 이득", "NEW_TOKEN과 session ticket을 끈 조건의 재방문 이득"),
        ("큰 cert H1", "quic-go IW 32 packet 조건의 큰 cert H1"),
        ("99.1% 적중", "고정 일정에서 m=3만 고른 99.1% 적중"),
        ("무손실을 배워 parity를 끈다", "c1 경로에서만 무손실을 배워 parity를 끈다"),
    ]:
        assert errors(tmp_path, unqualified)
        assert errors(tmp_path, qualified) == []


def test_frozen_errata_only_exempts_original_quote_cell(tmp_path):
    header = "| 파일 | 틀린 문장(원문 인용) | 맞는 문장 |\n|---|---|---|\n"
    quoted = "첫 비행 패리티 패딩 신용 핸드셰이크 증폭 제한 데이터그램 \u2014 \u2013 \U0001F680 1792 PASS 231"
    text = header + f"| 기록 | {quoted} | first flight |\n"
    assert errors(tmp_path, text, "docs/동결 세대 문서 정정표.md") == []
    for text in [header + f"| 기록 | 원문 | {quoted} |\n", header + "| 기록 | 원문 | 올바름 |\n\n" + quoted]:
        found = errors(tmp_path, text, "docs/동결 세대 문서 정정표.md")
        assert any("translated term" in error for error in found)
        assert any("em/en dash" in error for error in found)
        assert any("emoji" in error for error in found)
        assert any("obsolete test count" in error for error in found)
    assert errors(tmp_path, header + "| C:/local | 원문 | 올바름 |", "docs/동결 세대 문서 정정표.md")
    assert errors(tmp_path, header.replace("틀린 문장(원문 인용)", "다른 칸") + f"| 기록 | {quoted} | first flight |", "docs/동결 세대 문서 정정표.md")


def test_frozen_errata_empty_cells_and_unclosed_code_cannot_shift_exemption(tmp_path):
    header = "| 파일 | 틀린 문장(원문 인용) | 맞는 문장 |\n|---|---|---|\n"
    assert CHECK.cells("||원문|패딩|") == ["", "원문", "패딩"]
    for row in ["||원문|패딩|", "| 기록 | 원문 ` | 패딩 |", "| 기록 | 원문 | 패딩 ||"]:
        found = errors(tmp_path, header + row, "docs/동결 세대 문서 정정표.md")
        assert any("translated term" in error for error in found)
    assert CHECK.cells("| 기록 | ``인용 ` 안의 | 문자`` | 교정 |") == ["기록", "``인용 ` 안의 | 문자``", "교정"]
    assert any("malformed table row" in error for error in errors(tmp_path, header + "| 기록 | 원문 ` | 교정 |", "docs/동결 세대 문서 정정표.md"))


def test_early_canonical_skips_missing_and_root_readme(tmp_path, capsys):
    write(tmp_path, "README.md", "예측이 맞는다")
    assert CHECK.main(["--root", str(tmp_path), "--canonical"]) == 0
    assert "pending canonical" in capsys.readouterr().out
    assert CHECK.main(["--root", str(tmp_path), "--canonical", "--final"]) == 1
    output = capsys.readouterr().out
    assert "README.md:1: forbidden claim" in output
    assert all(name + ": missing document" in output for name in CHECK.CANONICAL)


def test_fixed_table_separates_external_paths_and_checks_baseline(tmp_path, monkeypatch):
    fixed_table(tmp_path)
    calls = []
    def fake_git(root, *args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "docs/fixed.md\n" if args[0] == "diff" else "", "")
    monkeypatch.setattr(CHECK, "git", fake_git)
    found, notes = CHECK.check_fixed(tmp_path)
    assert found == ["fixed document differs from baseline: docs/fixed.md"]
    assert "protected external paths 1" in notes[0]
    assert calls[-1] == ("diff", "--name-only", CHECK.BASELINE, "--", "docs/fixed.md")


def test_fixed_table_missing_baseline_and_missing_table(tmp_path, monkeypatch):
    fixed_table(tmp_path)
    monkeypatch.setattr(CHECK, "git", lambda root, *args: subprocess.CompletedProcess(args, 128, "", "absent"))
    found, notes = CHECK.check_fixed(tmp_path)
    assert found == []
    assert any("기준 커밋 없음" in note for note in notes)
    write(tmp_path, "docs/재현 절차.md", "## 8. 다른 절\n")
    assert CHECK.check_fixed(tmp_path)[0]


def test_fixed_table_outside_section_nine_does_not_count(tmp_path):
    path = fixed_table(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("## 9.", "## 8."), encoding="utf-8")
    assert CHECK.fixed_documents(tmp_path)[2]


def test_index_fallback_and_loop_record_grouping(tmp_path, monkeypatch):
    monkeypatch.setattr(CHECK, "git", lambda root, *args: subprocess.CompletedProcess(args, 128, "", "not a repository"))
    write(tmp_path, "docs/a.md")
    write(tmp_path, "docs/loop_record/raw.md", "F999\n")
    write(tmp_path, "docs/README.md", "[색인](README.md) [A](a.md) [기록](loop_record/)\n")
    found, notes = CHECK.check_index(tmp_path)
    assert found == []
    assert "docs 2/2 listed" in notes
    write(tmp_path, "docs/README.md", "[색인](README.md) [기록](loop_record/)\n")
    assert CHECK.check_index(tmp_path)[0] == ["unlisted document: docs/a.md"]
    write(tmp_path, "docs/README.md", "[색인](README.md) [A](a.md)\n")
    assert CHECK.check_index(tmp_path)[0] == ["docs/loop_record: missing grouped index entry"]


def test_ids_find_missing_definitions_and_skip_loop_records(tmp_path):
    write(tmp_path, "docs/용어와 ID.md", "F40 CP-02 A2r1-09 D1~D3 Q-22\n")
    write(tmp_path, "README.md", "F40 CP-02 A2r1-09 D2 Q-22\n")
    write(tmp_path, "docs/loop_record/raw.md", "F999\n")
    assert CHECK.check_ids(tmp_path)[0] == []
    write(tmp_path, "docs/current.md", "F41\n")
    assert CHECK.check_ids(tmp_path)[0] == ["docs/current.md:1: undefined ID: F41"]


def test_claims_requires_all_fourteen_types_in_table(tmp_path):
    statements = ["v3.3이 v3.2보다 낫다", "실측으로 개선 확인", "같은 바이트가 credit과 복구를 함께 산다",
                  "추가 비용 없는 FEC", "어디서나 나쁘지 않다", "예측이 맞는다", "적응이 이득을 냈다",
                  "PQ handshake의 증폭 병목을 우리가 밝혔다", "재방문 이득", "큰 cert H1", "99.1% 적중",
                  "유의차 없음이라 기각", "무손실을 배워 parity를 끈다", "PTO 12.0% 대 10.4%, z=0.79"]
    table = "| 금지 주장 | 대체 문장 |\n|---|---|\n" + "".join(f"| {value} | 근거 범위만 기록 |\n" for value in statements)
    write(tmp_path, "docs/CLAIMS.md", table)
    assert CHECK.check_claims(tmp_path) == ([], ["claims 14/14 covered"])
    write(tmp_path, "docs/CLAIMS.md", table.replace("| 예측이 맞는다 | 근거 범위만 기록 |", "| 예측이 맞는다 | 근거 | 여분 |"))
    assert CHECK.check_claims(tmp_path)[0] == ["CLAIMS table missing forbidden type: prediction"]
    write(tmp_path, "docs/CLAIMS.md", table.replace("| 예측이 맞는다 | 근거 범위만 기록 |\n", "") + "\n예측이 맞는다\n")
    assert CHECK.check_claims(tmp_path)[0] == ["CLAIMS table missing forbidden type: prediction"]


def test_cli_file_returns_nonzero_for_forbidden_claim(tmp_path):
    path = write(tmp_path, "docs/bad.md", "PTO 12.0% 대 10.4%, z=0.79로 기각")
    result = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), "--root", str(tmp_path), "--file", str(path)],
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1
    assert "forbidden claim: old_pto" in result.stdout
