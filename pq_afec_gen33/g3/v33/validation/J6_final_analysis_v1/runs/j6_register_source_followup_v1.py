import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
state_path = BASE / "state/LOOP_STATE.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
assert state["iterations"] == 21 and state["current"] == "J6"
assert state["tasks"]["J6"]["status"] == "doing"
extra = BASE / "state/EXTRA_TASKS.md"
before = {str(extra): sha(extra), str(state_path): sha(state_path)}
heading = "## J6에서 확인한 기존 과제의 후속 범위 (반복22)"
assert heading not in extra.read_text(encoding="utf-8")
note = """

## J6에서 확인한 기존 과제의 후속 범위 (반복22)

다음은 기존 카드의 입력·검증 범위를 보충한다. 과제 순서나 의존을 바꾸지 않는다. 근거는 runs/J6_historical_preflight_v1.md, J6_historical_k_anomalies_v1.json, J6_quic_source_read_v1.md, L5_reading_during_J6_v1.md, J6_L5_history_availability_note_v2.md다.

- O4: first_flight_datagrams는 flushFlight의 첫 버퍼 묶음 계수다. 완성된 ClientHello의 natural_k와 구분하고, ML-KEM 성공7행의 계수1을 자연 k=1 성공으로 해석하지 않는다. 당시 타이머가 개별 예외의 원인이었는지는 미확인이다. 새 ClientHello 길이·W 기반 입력의 시험에는 분할 버퍼와 첫 연결을 포함한다.
- R3: Go 소스의 ML-KEM 캡슐화 키1184 B와 X25519 공개키32 B의 합1216 B는 key_share 데이터다. 전체 ClientHello나 QUIC 데이터그램 크기가 아니다. 감사의 k2 행수93992·3596·6은 재현됐지만 모든 ML-KEM 행이 k2라는 서술은 계수1 예외7행 때문에 쓰지 않는다. W1452의 자연 k와 실제 패킷 분할은 확인한 근거 범위만 적는다. 서버 중앙값10991/10993/10949 B는 cert9007/9008/9006의 서로 다른 DER 크기이며 같은 인증서의 짝비교가 아니다.
- L5: 완료 연결의 실제 수신 data index로 중복을 제거하는 세계 관측 근사를 검토한다. index는 실제 QUIC 재전송의 패킷 번호나 CRYPTO 구간과 같지 않다. C1 rxRetx는 업링크 CRC 개수이므로 다운링크 바이트에서 빼지 않는다. p13 결과·보관본5개에 개별 tx_sizes/tx_ns 목록이 없고, H c12000에 없는 N·tail을 임의로 채워 n_need11을 만들지 않는다. 두 산출법의 앵커 적합과 과거 독립 검증을 구분한다.
- G1·T4: J6의 수신 작은 Initial 목록과 목적지 중앙값은 Python·세계 관측 계약이다. 실제 Initial 분류, 첫 큰 응답 이전 범위, ACK 유실에 따른 수신량과 서버 송신량의 차이, 같은 ACK를 S와 A_pre에서 두 번 세지 않는 조건을 각각 확인한다. ±13 B 단위 시험은 임의 ACK 손실까지 보장하지 않는다. 실제 wire 효과와 산술 거울은 기존 카드의 관문으로 확인한다.
"""
with extra.open("a", encoding="utf-8", newline="\n") as stream:
    stream.write(note)
source_files = [RUNS / name for name in (
    "J6_historical_preflight_v1.json", "J6_historical_k_anomalies_v1.json", "J6_quic_source_read_v1.json",
    "L5_reading_during_J6_v1.md", "L5_history_availability_during_J6_v2.json")]
record_path = RUNS / "J6_source_followup_registered_v1.json"
for tid in ("O4", "R3", "L5", "G1", "T4"):
    assert tid in state["tasks"]
    state["tasks"][tid].setdefault("handoff_notes", []).append(str(record_path))
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
result = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
          "tasks": ["O4", "R3", "L5", "G1", "T4"], "text": note,
          "files_before_sha256": before, "files_after_sha256": {str(extra): sha(extra), str(state_path): sha(state_path)},
          "source_sha256": {str(path): sha(path) for path in source_files}, "script_sha256": sha(__file__),
          "scope": "Existing task scope notes only; no adoption, dependency, order, policy, world, or benchmark change."}
with record_path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"tasks": result["tasks"], "record": str(record_path), "record_sha256": sha(record_path)}))
