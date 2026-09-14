# R&E: ML-KEM 적용 시 전송 성능 개선을 위한 QUIC 기반 적응형 FEC 연구

2026 R&E, 강원과학고등학교, 신레오·정도현·황요한, 지도 이현미.

비공개 연구 저장소다. 테스트용 CA 개인키는 포함하지 않는다.

| 폴더 | 내용 |
|---|---|
| [mlkem-quic-amplification](mlkem-quic-amplification/) | 팀 측정 코드, 원자료, 실험환경 명세와 연구 문서 |
| [pq_afec](pq_afec/) | 적응형 FEC와 PAD-FEC 알고리즘, Go 테스트베드, 검증 단계와 결과 |

ML-KEM이 ClientHello를 크게 만들면 QUIC의 증폭 제한에 사용할 수 있는 수신 바이트도 늘어난다. 이 연구는 인증서 크기와 손실 조건에 따라 그 변화가 핸드셰이크 시간에 미치는 영향을 측정하고, 패딩 증가량과 패리티 수를 고르는 정책을 검증한다.

제자리 FEC의 용량 조건 `C ≤ (k−1)(W−h−f)`는 측정한 12개 설정에서 성립하지 않았다. 이는 데이터그램 수와 크기를 고정한 첫 비행의 결과다.

quic-go v0.61.0에서 `InitialPacketSize`를 1280에서 1281로 올린 과거 측정은 특정 인증서 조건에서 약 1 RTT의 감소를 보였다. 증가량은 데이터그램당 1 B다. X25519(k=1)는 총 1 B, X25519MLKEM768(k=2)는 총 2 B를 더 보냈다. 패킷 단위 올림 모형은 해당 구현의 관찰이며, RFC가 송신량을 수신량의 3배보다 크게 허용한다는 뜻은 아니다. [RFC 9000 §8.1](https://www.rfc-editor.org/rfc/rfc9000.html#section-8.1).

팀 자료의 버스트 손실률 표기와 단방향·양방향 설정에는 이전 코드와 문서 사이의 불일치가 있다. 해당 README의 데이터 주의를 확인해야 한다. 유의한 차이를 찾지 못한 결과만으로 두 방식이 동등하거나 기존 연구 전제가 기각됐다고 단정할 수 없다.

측정은 Windows와 WSL Ubuntu에서 실행한다. 실제 측정 정본은 `C:\dev\pq_afec`이며, 이 저장소는 배포 사본이다. `results/*.json`에는 여러 날짜의 결과가 함께 있으므로, 실행 기록과 소스 지문을 함께 확인해야 한다.

```powershell
python pq_afec/experiments/loop2.py --status
```

실험별 조건과 한계는 [PADFEC 명세](pq_afec/docs/PADFEC%20v2%20명세.md)와 [팀 측정 README](mlkem-quic-amplification/README.md)에 기록한다.
