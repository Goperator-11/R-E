import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
names = ("experiments/quicbed/qamp.go", "experiments/quicbed/policy.go", "experiments/quicbed/policy3.go", "experiments/quicbed/build_gen33.sh", "experiments/quicbed/go.mod", "experiments/gate_v3_parity.py", "g3/policy3_reference_gen.py")
wsl = {"/home/scien/gopath/pkg/mod/github.com/quic-go/quic-go@v0.61.0/transport.go": "006aa5326518208604b5f39f6dac567040c4f56165bf250fb8bea22c12c9b0b1", "/home/scien/gopath/pkg/mod/github.com/quic-go/quic-go@v0.61.0/internal/protocol/connection_id.go": "9935062a2a72d2464da8197a2059b83a1c864f04a9aa5da6a3dc9f19a963fb8d", "/home/scien/gopath/pkg/mod/github.com/quic-go/quic-go@v0.61.0/internal/protocol/params.go": "de24ac6614e32eb6117db22d2c6d4b7c4ec92b9af216c50ef41e948af6593800"}
cases = [{"dcid_B": dcid, "scid_B": 4, "padding_B": 20-dcid, "base_B": 22+dcid+4+20-dcid} for dcid in range(21)]
assert all(case["padding_B"] >= 0 and case["base_B"] == 46 for case in cases)
note = """# J7 호출 경로와 빌드 보존 검토

L5 반복24의 고정 MC 계산 중 소스를 읽었다. J7 구현·시험·빌드는 아직 시작하지 않았고 L5 후보·동결 사본은 그대로다.

qamp.go의 fecConn.WriteTo는 새 비행 첫 데이터그램에서 dcid·scid를 복사한다. flushFlight의 gen-2와 v3 패리티 생성은 이 값을 buildParity에 그대로 전달한다. 클라이언트는 quic.Transport{Conn: fc}를 직접 만들며 ConnectionIDLength나 ConnectionIDGenerator를 지정하지 않는다. 읽은 quic-go v0.61.0 transport.go에서 이 직접 Transport의 isSingleUse는 기본 false이며, init(false)는 길이0 설정을 DefaultConnectionIDLength로 바꾼다. params.go의 기본값은4다. connection_id.go의 GenerateConnectionIDForInitial은8~20 B DCID를 만든다. 따라서 현재 첫 비행 호출의 SCID4·DCID8~20은 소스로 확인된다. 실행 중 실제 wire 검증은 아니다.

서버의 serverConnIDLength도4다. 이후 비행의 DCID4와 길이0 경계까지 포함해 SCID4·DCID0~20인21가지 산술을 저장했다. 본문 패딩20-len(DCID)를 선언된 blen에 포함하면 전체 크기는 W+46+6k다. 사용자 지정 CID 조합이나 SCID20·DCID20은 이46 B 기본값 안에 들어가지 않는다. J7 구현에서는 지원 범위를 명시하고 불가능한 조합을 거부해야 한다. nil 패킷을 WriteTo에 넘겨 성공 패리티로 세는 동작도 피해야 하며, 원본 전송 보존을 시험해야 한다. 아직 이 처리 방식의 구현이나 성능 판정은 하지 않았다.

parseFecBlock은 Initial·token length0·2 B 길이 표현을 요구하고, 선언된 본문에 PFEC가 있는지 검사한 뒤 need까지 읽는다. 실패 계수는 단순 부분열 검색으로 만들면 다른 패킷의 우연한 문자열을 잘못 셀 수 있다. 헤더와 본문 시작 위치를 사용하고, 잘린 길이·잘못된 버전·심볼 길이·CID 경계·유효 패딩을 구분하는 시험이 필요하다. off 모드에서 파싱을 생략하는 현재 계측 정의도 문서로 정해야 한다.

build_gen33.sh는 종료 trap의 cleanup에서 mktemp stage 폴더를 rm -rf로 지운다. 작업 계약은 저장소의 추적 파일을 git rm하는 경우 외에는 삭제를 금지한다. J7 빌드를 실행하기 전에 이 trap을 바꿔 stage 폴더를 남기고 경로를 기록해야 한다. 보호 경로를 복구하거나 과거 삭제 내용을 만들어 넣지 않는다. Go 자체의 내부 임시 파일 정리까지 보존하려면 별도 실행 환경 검토가 필요하며 현재 이 읽기에서는 빌드를 실행하지 않았다.

현재 정책 관문은 v3.2-dev 버전과 상태 궤적을 고정하고, Python 기준 벡터 생성기는 활성 learn3를 읽는다. L1의 상태4·도착 우도는 Go G1 이전 범위이므로 J7 전에 기존 기준 관문의 정확한 차이를 기록해야 한다. 그 차이를 숨기거나 J7 완료를 일부 산술 PASS로 대체하지 않는다. 세계39 B와 새 와이어46 B 자료를 같은 조건으로 합치지 않는 제약은 앞선 검토를 유지한다.
"""
value = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "during_task": "L5", "scope": "Read-only local source review and exact integer byte arithmetic; no Go build, execution or policy change", "source_sha256": {str(ROOT / name): sha(ROOT / name) for name in names}, "wsl_sources_sha256_observed": wsl, "CID_arithmetic": cases, "script_sha256": sha(__file__)}
for name, text in (("J7_reading_during_L5_v2.json", json.dumps(value, ensure_ascii=False, indent=2) + "\n"), ("J7_reading_during_L5_v2.md", note)):
    with (RUNS / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
print(json.dumps({"local_sources": len(names), "wsl_sources": len(wsl), "CID_arithmetic_cases": len(cases)}))
