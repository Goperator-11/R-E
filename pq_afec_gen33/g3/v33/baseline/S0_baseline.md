# S0 기준선

2026-10-30 KST. 자료 종류는 구현 검증이다. 네트워크 성능 측정은 하지 않았다.

| 검사 | 결과 |
|---|---|
| CRLF 정규화 비교 | gen32 226개, gen33 227개. 빌더 이름 교체와 gen33_parity_baseline.json 추가 외 차이 0개 |
| 핵심 pytest | 109 통과, 하위 검사 367 통과, 20.90초 |
| Go | vet 통과, 시험 101 통과, 빌드 통과. Go 1.26.6, quic-go v0.61.0 |
| Python·Go 내용 대조 | constants, primitives, decisions, trajectories, fresh 5절 통과 |
| 기준 벡터 | 원시값 2,800개, 결정 6,720개, 궤적 5개. 비용 최대 절대 차이 0 ms |
| 새 표본 | 원시값 2,600개, 결정 5,000개, 궤적 4개. 비용 최대 절대 차이 0 ms |
| 전체 관문 | FAIL. 빌더 이름 지문 불일치 1건만 발생. S0 카드가 허용한 기준선 상태이며 S3에서 수정 |

바이너리 SHA-256: `79ef209f88fe85f75fdd6f5ac8dac2547b28cff40ba901dc2d53aef8515a816d`.

빌더 srcsha: `61fc4f11fb05be6cf71af2e6fea75eab921348aa0fd503534992f15b3d9c1c53`.

관문 지문: `3edafb0d7b54cd0ef2610637fa528a17b72fbacb6482c5bd569a06a15b98cc0b`.

기준선 첫 커밋은 `90859b9`이며 브랜치는 `v33`이다. core.autocrlf는 false이고 작성자는 R-E 마지막 커밋의 설정을 사용했다.

## 고정 핵심 시험

```text
tests/test_core_regressions.py
tests/test_padfec3_learn.py
tests/test_padfec3_layout.py
tests/test_padfec3_dev_regressions.py
tests/test_padfec3_input_validation.py
tests/test_padfec3_followup.py
tests/test_replay_g3_dev.py
tests/test_gen32_runner_isolation.py
tests/test_adaptation_benchmark.py
```

S5 전까지 이 9개를 핵심 목록으로 사용한다. 실행 래퍼는 `C:\dev\codex_handoff\v33\runs\s0_pytest.py`이며 `python -I -B`로 실행한다.

## 재현

```powershell
python -I -B C:\dev\codex_handoff\v33\runs\s0_compare.py
python -I -B C:\dev\codex_handoff\v33\runs\s0_pytest.py
wsl -d Ubuntu -- bash /mnt/c/dev/pq_afec_gen33/experiments/quicbed/build_gen33.sh
wsl -d Ubuntu -- python3 -I -B /mnt/c/dev/pq_afec_gen33/experiments/gate_v3_parity.py --bin /home/scien/quicbed_gen33/bin/qamp --out /mnt/c/dev/codex_handoff/v33/runs/S0_gate_repeat.json
```

정규화 비교는 초기 사본을 검사한 기록이다. 이후 수정 뒤의 비교는 변경 내용을 보고하므로 초기 결과와 구별해야 한다. 빌더의 임시 경로 때문에 바이너리 해시는 재빌드마다 달라질 수 있고, 재현성 수정은 S3에 있다.

근거 파일: runs/S0_compare.json, S0_pytest.log, S0_build.log, S0_gate.json, S0_gate.log, S0_binary.log. 감사 A6-M05와 A6-05의 원문 및 verify-A6 정정을 확인했다.
