import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
ROOT = Path(r"C:\dev\pq_afec_gen33")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
sources = [BASE / "prompt/TASKS.md"] + [BASE / "findings" / name for name in ("FINDINGS_INDEX.md", "audit-cost-model.md", "verify-A1.md", "audit-prior-art.md", "verify-A7.md", "audit-quicgo-source.md")]
sources += [ROOT / name for name in ("experiments/quicbed/qamp.go", "experiments/v33/worldsim.py", "padfec3/layout.py")]
note = """# M1 사전 읽기와 선행 알고리즘 확인

반복24의 L5 보고서 생성 중 읽은 범위다. M1을 시작하거나 구현·시험한 기록은 아니다. M1을 선택하는 반복에서 카드와 연결 감사 전체를 다시 읽어야 한다. 이번에 본 layout.py는 아직 미채택 L5 후보 상태다.

M1 카드는 선행을 RS 심볼로 유지하면서 보류하고, 마지막 원본·첫 뒤 패리티·예정 도착 기한 중 먼저 온 시점에 처리하도록 요구한다. A7-17 검증자는 실제 마지막 도착 뒤 타이머를 잡으면 잃어버린 꼬리를 서버가 미리 아는 오류라고 지적했다. 검증자가 보정한 큰 cert 15%의 약10.5~11.6 ms 감소는 기존 model-world 값이며 이번에 재실행한 수치가 아니다. 기존 감사의 최대14 ms를 새 독립 세계 결과로 쓰지 않는다.

로컬 qamp.go는 Cauchy 행렬을 사용하며 m=1은 XOR다. cauchyRow는 x=p, y=m+o의 역수를 쓰고, recoverMany는 소거 원본 수만큼의 서로 다른 패리티 행을 고른다. 현재 creditLocked는 선행을 즉시 stackLocked하고 복구 기록에 보존하지 않는다. 따라서 보류 구현은 심볼 가용성과 실제 스택 신용을 함께 바꿔야 한다. 코드의 설명만으로 새 보류 경로의 회계 불변식이나 모든 순열을 검증했다고 쓰지 않는다.

W0 worldsim.py에는 lead_mode=buffered가 이미 있다. 첫 비행의 조합 검사는 timing_included=False이고, 사건 실행은 전체 송신 슬롯의 직렬화 시간과 half_rtt·hold_margin_ms를 더해 기한을 예약한다. 마지막 원본과 뒤 패리티에서 force=True로 복호를 시도한다. 이 세계가 알고 있는 송신 시작·업링크 속도·남은 슬롯을 실제 서버가 어떻게 알 수 있는지는 별도 계약이 필요하다. 실제 구현에서 관측할 수 없는 값을 기한 입력으로 몰래 쓰면 안 된다. 기존 동결 세계를 덮어쓰지 않고, 새 구현에 필요한 세계 변경은 별도 판본·사전 계획으로 다뤄야 한다.

RFC 8681 §6.2의 RLC 수신기는 받은 원본·복구 심볼로 선형계를 유지하며, 복구할 부분계의 rank가 충분할 때 해를 구한다. 같은 수의 심볼이 도착했다는 사실만으로 항상 복구된다고 하지는 않는다. 이 설명은 선행 심볼의 정보를 버릴 필요가 없다는 설계 참고이며, PAD-FEC의 Cauchy 부호·신용 회계·기한 비용을 대신 증명하지 않는다. [RFC 8681 §6.2](https://www.rfc-editor.org/rfc/rfc8681.html#section-6.2)

감사에 인용된 QUIC RLC 문서 03판은 2020년3월9일의 개인 Internet-Draft이며 현재 만료·보관 상태다. §4.2.2는 RFC 8681의 복호 절차를 참조한다. 이를 현재 QUIC 표준이나 Initial 증폭 신용을 보장하는 규칙으로 제시하지 않는다. [QUIC RLC draft 03](https://datatracker.ietf.org/doc/html/draft-roca-nwcrg-rlc-fec-scheme-for-quic-03#section-4.2.2)

M1 구현 전 남은 검토는 관측 가능한 기한 기준, 재정렬·중복·늦은 원본, 비행별·전체 보류 상한과 TTL, 충분한 rank가 생긴 순간의 복호와 신용 방출 순서, 실패·손상 심볼 처리다. 선행을 비RS 패딩으로 바꾸는 A1-11 제안은 카드의 금지와 검증자의 doubtful 판단을 유지한다. 순열·소거 대조와 현실적 기한 비용의 새 수치는 아직 없다.
"""
value = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "during_task": "L5", "task_reviewed": "M1", "scope": "Read-only source and primary literature review; no M1 implementation, tests or performance rerun", "source_sha256": {str(path): sha(path) for path in sources}, "web_sources": [{"url": "https://www.rfc-editor.org/rfc/rfc8681.html", "section": "6.2", "accessed_kst_date": "2026-10-31"}, {"url": "https://datatracker.ietf.org/doc/html/draft-roca-nwcrg-rlc-fec-scheme-for-quic-03", "section": "4.2.2 and status", "accessed_kst_date": "2026-10-31"}], "script_sha256": sha(__file__)}
for name, text in (("M1_reading_during_L5_v1.json", json.dumps(value, ensure_ascii=False, indent=2) + "\n"), ("M1_reading_during_L5_v1.md", note)):
    with (RUNS / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
print(json.dumps({"local_sources": len(sources), "primary_web_sources": len(value["web_sources"])}))
