# R&E: ML-KEM 적용 시 전송 성능 개선을 위한 QUIC 기반 적응형 FEC 연구

2026 R&E, 강원과학고등학교, 신레오·정도현·황요한, 지도 이현미.

비공개 연구 저장소다. 테스트용 CA 개인키는 포함하지 않는다.

## 폴더

| 폴더 | 내용 |
|---|---|
| [mlkem-quic-amplification](mlkem-quic-amplification/) | 팀 측정 코드, 원자료, 실험환경 명세와 연구 문서 |
| [pq_afec](pq_afec/) | gen-2. 적응형 FEC와 PAD-FEC v2 알고리즘, Go 테스트베드, 검증 단계와 결과 |
| [pq_afec_gen3](pq_afec_gen3/) | v3.0. 첫 비행의 선행 신용 데이터그램과 복구 패리티를 따로 고르는 정책, 0·2단계 봉인 측정 |
| [pq_afec_gen31](pq_afec_gen31/) | v3.1. 완료 판정 수정, 명목 2-RTT 관측의 학습 제외, 잔차 감시층 추가. 3단계 봉인 측정 |
| [pq_afec_gen32](pq_afec_gen32/) | v3.2 개발본. 학습·후보·캐시 수정, 구현 대조와 합성 적응 벤치. 실측 없음 |
| [docs/audit-2026-09-14](docs/audit-2026-09-14/) | 2026-09-14 추가 감사의 근거표와 출처 점검 |

세대마다 폴더를 따로 둔다. 다음 세대는 앞 세대 폴더의 사본을 떠서 고치므로 `afec/`, `padfec/` 같은 공통 코드가 폴더마다 겹친다. 같은 실행 안에서 두 세대를 나란히 재려고 이렇게 했다.

## 세대별 현황

| 세대 | 측정 | 판정 |
|---|---|---|
| gen-2 (`pq_afec`) | 2026-10-01~10-02 실행 | 18단계 통과, 6단계 실패(p8 p10 p15 p17 p18 p20), p6 미실행(이전 done은 stale). p16은 10월 1일 실패 뒤 10월 2일 재실행에서 통과. 10월 2일·7일 코드 수정 뒤 새 실측 없음 |
| v3.0 (`pq_afec_gen3`) | 2단계, 2026-10-02 두 회차 | H1 개선 주장 성립(큰cert +28.18 ms, RTT200 +11.35 ms). H2 실패(보류 셀 1개 열등), H3 통과, H4 적응 기여 확인 안 됨 |
| v3.1 (`pq_afec_gen31`) | 3단계, 2026-10-02~10-03 두 회차 | H1 개선 주장 성립(큰cert +28.01 ms, RTT200 +12.38 ms). H2 실패(판정불능 1), H3 실패, H4 적응 기여 확인 안 됨 |
| v3.2-dev (`pq_afec_gen32`) | 없음 | 구현 검사만 통과. [v3.2 검증 기록](pq_afec_gen32/g3/development_validation/README.md) |

판정 근거는 각 폴더의 `g3/RESULT_*.md`와 `experiments/results/*_decisions.json`이다. 앞 세대의 판정을 다음 세대 개발본의 성능으로 쓰지 않는다. v3.1 폴더의 `SEAL_stage0.json`과 `SEAL_stage2.json`은 v3.0에서 물려받은 봉인이라 v3.1에서 고친 파일과 해시가 다르다. 그 두 봉인은 `pq_afec_gen3`에서 대조한다.

## 연구 요약

ML-KEM이 ClientHello를 크게 만들면 QUIC의 증폭 제한에 사용할 수 있는 수신 바이트도 늘어난다. 이 연구는 인증서 크기와 손실 조건에 따라 그 변화가 핸드셰이크 시간에 미치는 영향을 측정하고, 패딩 증가량과 패리티 수를 고르는 정책을 검증한다.

제자리 FEC의 용량 조건 `C ≤ (k−1)(W−h−f)`는 측정한 12개 설정에서 성립하지 않았다. 이는 데이터그램 수와 크기를 고정한 첫 비행의 결과다.

quic-go v0.61.0에서 `InitialPacketSize`를 1280에서 1281로 올린 과거 측정은 특정 인증서 조건에서 약 1 RTT의 감소를 보였다. 증가량은 데이터그램당 1 B다. X25519(k=1)는 총 1 B, X25519MLKEM768(k=2)는 총 2 B를 더 보냈다. 패킷 단위 올림 모형은 해당 구현의 관찰이며, RFC가 송신량을 수신량의 3배보다 크게 허용한다는 뜻은 아니다. [RFC 9000 §8.1](https://www.rfc-editor.org/rfc/rfc9000.html#section-8.1).

팀 자료의 버스트 손실률 표기와 단방향·양방향 설정에는 이전 코드와 문서 사이의 불일치가 있다. 해당 README의 데이터 주의를 확인해야 한다. 유의한 차이를 찾지 못한 결과만으로 두 방식이 동등하거나 기존 연구 전제가 기각됐다고 단정할 수 없다.

## 로컬 원본과 실행

측정은 Windows와 WSL Ubuntu에서 실행한다. 이 저장소는 배포 사본이고, 측정을 돌리는 원본은 정도현 노트북의 다음 폴더다.

| 저장소 폴더 | 로컬 원본 |
|---|---|
| `pq_afec` | `C:\dev\pq_afec` |
| `pq_afec_gen3` | `C:\dev\pq_afec_gen3` |
| `pq_afec_gen31` | `C:\dev\pq_afec_gen31` |
| `pq_afec_gen32` | `C:\dev\pq_afec_gen32` |

v3 세대 폴더에는 측정 원자료(`experiments/state/`의 저널)와 그림을 올리지 않았다. 판정 파일과 봉인에 들어간 결과만 있다. `pq_afec`는 원자료까지 올리며, `results/*.json`에 여러 날짜의 결과가 함께 있으므로 실행 기록과 소스 지문을 함께 확인해야 한다. `pq_afec/experiments/results/p17_adaptive_value.json`은 58.6 MB다.

```powershell
python pq_afec/experiments/loop2.py --status
```

실험별 조건과 한계는 [PADFEC 명세](pq_afec/docs/PADFEC%20v2%20명세.md)와 [팀 측정 README](mlkem-quic-amplification/README.md)에 기록한다.

## 봉인 파일 확인

새 clone의 줄바꿈은 루트 .gitattributes가 LF로 고정한다. 다음 명령은 추적된 상대경로의 봉인·추가 기록 파일을 원본 바이트로 확인한다. 외부 원자료·바이너리·절대경로 개발자료는 로컬 보존 manifest로 별도 확인해야 한다.

```powershell
python -I -B tools/verify_seals.py
```

gen-2 최종 상태의 근거는 pq_afec/experiments/state/fixloop_triage.json과 loop2.json의 p16 history다. p6은 과거 done이지만 마지막 분류가 stale이므로 현재 통과 수에 포함하지 않았다.
