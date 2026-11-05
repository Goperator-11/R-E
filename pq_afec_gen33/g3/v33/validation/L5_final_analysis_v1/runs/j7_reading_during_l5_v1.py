import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
sources = [ROOT / name for name in ("experiments/quicbed/qamp.go", "experiments/quicbed/policy.go", "experiments/quicbed/policy3.go",
    "padfec/policy.py", "padfec/quantum.py", "padfec3/decide3.py", "padfec3/layout.py", "experiments/gate_v3_parity.py",
    "g3/policy3_reference_gen.py", "experiments/v33/worldsim.py", "experiments/v33/worldparams.json")]
sources += [BASE / "findings" / name for name in ("audit-go-wire.md", "audit-gen2-foundation.md", "audit-quicgo-source.md")]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
checks = [{"dcid_bytes": dcid, "scid_bytes": 4, "original_overhead_base_B": 22 + dcid + 4,
           "proposed_zero_padding_B": 46 - (22 + dcid + 4)} for dcid in range(8, 21)]
assert all(row["original_overhead_base_B"] + row["proposed_zero_padding_B"] == 46 for row in checks)
note = """# J7 소스 사전 검토

L5 합동 입력 검증 중 읽기만 수행했다. J7의 구현·시험을 시작한 기록이 아니다. L5 활성 후보와 모든 동결 사본은 바꾸지 않았다.

연결 감사 A3-05·A4-02·A8-05의 본문을 읽었다. buildParity의 헤더·본문 길이는 symLen + 22 + 6k + len(DCID) + len(SCID)다. parseFecBlock은 선언된 blen 범위에서 need 이하인지 확인하고 필요한 symLen만 복사하므로, 선언된 본문 끝의 여분 바이트를 읽지 않는다. J7의 패딩은 길이 선언에 포함해야 한다.

SCID4와 DCID8..20을 가정하면 추가할 바이트는12..0이고 합은 W+46+6k다. 이는 소스의 길이 식을 계산한 결과이며 실제 Go 실행 검증은 아직 하지 않았다. 임의 SCID20까지 포함하면46이라는 고정 기본값으로 모두 수용할 수 없다. 현재 호출의 CID 범위를 확인하고 지원하지 않는 조합의 동작을 성능 전에 명시해야 한다.

Python policy의 PARITY_OVERHEAD_BASE와 Go parityDatagramBytes는39다. v3 후보 상한은 양쪽 모두1500-28=1472이고 gen-2 경로도 같은 제한을 사용한다. J7의46·1452 계약에서는 k1/2/4의 패리티가 허용하는 W 상한이1400/1394/1382 B다. 원본 Initial 상한1452와 패리티 전체 상한1452를 구분해야 한다.

decodeConn.ReadFrom은 수신·분류 뒤 mu를 잠그고 BytesIn과 연결별 원본/패리티 바이트를 센다. 현재 파싱 실패는 fb=nil인 원본 경로로 간다. 새 실패 계수는 유효한 패리티와 임의 payload의 우연한 PFEC 문자열을 구분하도록 헤더·본문 위치를 정해야 한다. off 모드는 원래 파싱을 생략하므로 계측 정의도 따로 명시해야 한다.

세계 모형의 fec.parity_overhead_base는39이고 출처 문구도 미래 J7 형식이 아니라고 명시한다. _parity_size는 이 매개변수를 사용하므로 동결 worldsim.py를 고치지 않고46 B 개발 프로파일을 줄 수 있다. 다만 기존 L1 원자료는39 B 세계에서 수집했다.46 B 수집에 그 원자료를 같은 세계의 짝비교로 붙이면 안 된다. 원래39 B 프로파일의 정책 비교와 새 와이어46 B 프로파일의 비교 범위를 분리하고, 새 프로파일에서 비교할 기준 정책도 동일한 조건으로 재수집하는 계획이 필요하다. 아직 이 계획을 채택하거나 실행하지 않았다.

현재 정책 관문은 v3.2-dev 표기와 학습 궤적·상태 비교를 포함한다. 활성 L1의 C1·상태4 거울이 Go에 반영되지 않은 범위는 G1에서 처리할 예정이므로 J7 관문에서 기존 차이와 새 크기 변경의 차이를 구분해야 한다. L5 상태9는 채택되지 않은 후보이며 J7 기준으로 넘기지 않는다. 완료 기준을 일부 비교의 PASS로 낮추지 않는다.
"""
result = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "task": "J7",
    "during_task": "L5", "scope": "source reading and elementary byte arithmetic only; no J7 implementation or transport execution",
    "sources_sha256": {str(path): sha(path) for path in sources}, "padding_arithmetic": checks,
    "W_cap_B": {str(k): 1452 - 46 - 6 * k for k in (1, 2, 4)}, "script_sha256": sha(__file__)}
for name, value in (("J7_reading_during_L5_v1.json", json.dumps(result, indent=2) + "\n"), ("J7_reading_during_L5_v1.md", note)):
    with (RUNS / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)
print(json.dumps({"status": "recorded", "sources": len(sources), "CID_cases": len(checks)}))
