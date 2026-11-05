import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
ROOT = Path(r"C:\dev\pq_afec_gen33")
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
diagnosis = read(RUNS / "L5_c12000_diagnosis_v1.json")
protocol_path = ROOT / "g3/v33/bench_protocol.json"
scenario = next(s for s in read(protocol_path)["scenarios"] if s["id"] == "B12_c12000")
assert scenario["context"]["k"] == 2 and scenario["context"]["w"] == 1280
assert scenario["world_params"] == {}
groups = diagnosis["groups"]
assert all(g["runs"] == 20 and g["rows_including_warmup"] == 27000 for g in groups.values())
assert len(groups) == 7
assert all(g["parity_oversize_rows"] == (0 if name.startswith("L1:") else 26980) for name, g in groups.items())
lines = ["# L5 c12000의 패리티 수신 한도 진단", "",
"전체 평가를 마친 뒤 원자료만 읽어 진단했다. 후보나 세계를 바꾸거나 추가 성능 표본을 만들지 않았다. L5_c12000_diagnosis_v1.py가 독립 검사에 묶인 140개 추적의 SHA를 확인했고, 189000행을 집계했다. 아래 수에는 각 실행의 첫 cold 연결도 들어 있다.", "",
"c12000에서 L5 full none·C1·ideal과 single none·C1은 각각 27000연결 중26980연결에서 수신 한도를 넘는 패리티를 골랐다. 나머지20연결은 각 seed의 첫 cold 연결이다. L1 none·C1의 초과는 각각0연결이다. full none·C1과 single none·C1은 행동별 횟수까지 같다.", "",
"후보의 δ130은 W=1410 B다. 기존39 B 세계에서 k2 패리티는1410+39+12=1461 B이며 서버 decoder 한도1452 B를9 B 넘는다. 정책은1472 B까지 허용한다. worldsim.py의 server_receive는 수신 크기를1452 B로 자르고 parity_truncated를 기록한 뒤 복구 분기를 건너뛴다. 잘린 바이트는 신용에 계상된다. 이는 코드와 고정 원자료가 드러낸 계약 불일치다.", "",
"L5 C1의 관측 사유는 receiver_capacity_censoring 26195회, feedback_missing 785회, 첫 연결의 c1_snapshot 20회다. 손실 갱신은 categorical 26980회, datagram20회다. full C1의 참 p=0.08 구간에서 결정 전 p_mean 평균은" + format(groups["L5_v1:c1"]["phases"]["1"]["mean_p_pre"], ".6f") + ", L1 C1은" + format(groups["L1:c1"]["phases"]["1"]["mean_p_pre"], ".6f") + "이다. ideal은 도착 정보를 받지만 동일한 크기 초과가 남는다. 이 진단만으로 악화24.9 ms 전체를 잘림 한 요인에 분해하지는 못한다.", "",
"완료 데이터는 L5의 다섯 팔 모두 각27000행에서 S13934 B, prefix12800 B, n_need11이다. 과거 유효 모형의12→11 보정과 일치하는 n_need만으로 행동이 안전해지지 않는다. 수신 가능한 후보 집합, 잘림과 손실의 구분, 관측 우도를 함께 확인해야 한다.", "",
"J7에1452 B 상한과 실제 wire 길이의 일치를 연결한다. E11은 J7·T4 뒤 L5의 크기 산술과 관측을 다시 검토한다. J7의 새46 B 세계에서는 이전39 B 원자료를 같은 세계의 기준선으로 재사용하지 않는다. 기존L5 판정은 그대로 보존하고 새 후보 계획은 평가 전에 고정한다.", "",
"기여 분리 실험, 실제 QUIC 패킷 잘림과 c12000 재측정은 아직 하지 않았다. 역사 N·tail·완료 패킷목록의 부재도 해결되지 않았다.", "",
"출처: L5_c12000_diagnosis_v1.json, L5_bench.md, experiments/v33/worldsim.py:776 및794, 동결 L5_v1/padfec3/decide3.py의 UDP_MAX와 후보 필터.", ""]
path = RUNS / "L5_c12000_diagnosis_v1.md"
with path.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("\n".join(lines))
with (RUNS / "L5_c12000_note_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"script_sha256": sha(__file__), "note_sha256": sha(path), "diagnosis_sha256": sha(RUNS / "L5_c12000_diagnosis_v1.json"), "protocol_sha256": sha(protocol_path)}, stream, indent=2)
    stream.write("\n")
print(path)
