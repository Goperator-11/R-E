# J3 실패 비용 진단 계획

2026-11-02 정정: 아래 둘째 문단의 "현재 기본 후보"와 "현재 T6 후보"는 T6가 `original_first`를 qamp 기본값으로 둔 2026-11-01 상태를 말한다. 지금 qamp `-retrans-layout` 기본값은 다시 `repeat_first`이고 `original_first`는 `-retrans-layout original_first`로 명시할 때만 쓴다(루프 결정 D43이 D28을 대체). 계획 본문과 결과(`docs/J3_reference_result.md`)는 그때 고정한 그대로 둔다. 근거는 `docs/V33FIX_testbed.md`(F4 절과 통합 정리 절)와 `C:\dev\codex_handoff\v33\state\DECISIONS_NEEDED.md`의 D43이다.

기존 고정 팔 저널 p31_run1_S_bigcert_units.jsonl과 p31_run2_S_bigcert_units.jsonl을 읽어 run·손실률별 g3fixL3를 집계한다. 실패 대용은 기존 검증자와 같은 ok=false 또는 initial_datagrams≥4다. HCT·대용 빈도·Initial 수·parity 수·유효 MinRTT를 보존한다. 이 조건은 실제 실패 종류나 재송신 CRYPTO 구간의 라벨이 아니다. 봉인 자료를 읽는 개발 분석이며 원래 봉인 판정은 변경하지 않는다.

기준 입력은 k2·W1280·u2·n_need15, 경로 RTT50 ms다. 기존 검증자의 RTT50.7 ms 계산도 별도 재현한다. 기존 비용을 계산하고 현재 기본 후보, 경로 RTT만 쓰는 후보, repeat_first·missing, repeat_first·all, original_first·all을 모두 고정해 대조한다. 결과를 보고 가장 잘 맞는 범위를 채택하지 않는다. 과거 와이어의 재보호 모양에 맞춘 repeat_first 진단과 현재 T6 후보를 같은 비교로 읽지 않는다. ±10 ms 기준과 terminal_probability를 전부 공개한다.

알려진 p의 모형 결정 표는 k2·W1280·S18232 B, u={0,2,5,10} Mbps, RTT={50,120,200} ms, p={0,0.02,0.08,0.15,0.25,0.30}의 72문맥이다. 기존 candidates3·J_TIE·tie_key를 그대로 사용하고 각 후보의 기존 J와 새 두 단계 J를 비교한다. 후보별 k는 기존 고정 k 모형 가정이며 O4의 현재 CH 평가가 아니다. 재평가·학습·감시의 효과를 포함하지 않는 알려진 입력 진단이다.

dry-run은 계획·두 입력 저널·소스 해시를 검사한다. smoke는 고정 팔 자료를 그대로 모두 읽고, 결정 표의 앞 4문맥만 계산한다. full은 72문맥 전부를 계산한다. 결과 파일은 별도 폴더에 새로 쓰고 입력·소스 해시를 실행 전후 비교한다. 활성 정책과 W1 소스는 변경하지 않는다.
