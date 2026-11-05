# Python 부호기와 테스트베드 형식

S5에서 확인한 구현 사실을 R3 문서 작업의 입력으로 남긴다. 모든 길이는 B다.

`padfec/codec.py`의 시험용 footer는 `>4sBHBBBHI` 형식의 16 B다. magic 4, version 1, flight 2, index 1, k 1, m 1, 원래 길이 2, 해당 심볼 CRC32 4로 구성된다. `padfec/capacity.py`의 DEFAULT_F=16은 이 모형 형식의 상수다.

Go `experiments/quicbed/qamp.go`의 buildParity는 다른 형식이다. FEC 본문 앞부분은 magic 4, version 1, flight 2, k 1, m/lead 1, index 1, symLen 2로 12 B다. 이어 원본별 CRC32 목록 4k B, 원본 길이 목록 2k B와 패리티 심볼이 붙는다. 이 본문을 감싸는 헤더는 현재 코드에서 10+len(DCID)+len(SCID) B다. 따라서 이 함수가 만드는 패리티 데이터그램은 심볼 길이+22+len(DCID)+len(SCID)+6k B다. CID 길이를 모르면 고정 16 B를 더해 와이어 길이라고 부를 수 없다.

`padfec/policy.py`의 parity_datagram_bytes는 실측 근사 기본값 39 B와 원본별 6 B를 사용한다. 이 39는 모든 CID 조합에서 buildParity가 보장하는 상수가 아니다. S5는 16, 39, 또는 별도 실측 프로파일을 서로 치환하지 않았다. 와이어 프로파일을 채택하는 과제는 실제 CID·길이 근거와 정책 관문을 따로 검증해야 한다.

`RSErasureCode(k, 1)`은 S5부터 계수 한 행을 전부 1로 사용한다. XOR 패리티와 같고 `FlightCode`의 단일 패리티 경로와 호환된다. 다중 패리티는 기존 Cauchy 계수를 유지한다. 그 행렬은 전체 패리티 수에 의존하므로 m을 바꾸고 기존 패리티를 그대로 더 쓰는 증분 부호라고 해석하지 않는다. 독립 XOR과 k=1,2,3,16,255의 소거 복구 25경우를 시험했다.

lead는 실제 패리티로 유지한다. A4-10의 신용 전용 무작위 바이트 제안은 채택하지 않는다. 수신 hold 경로에서 실제 복구 심볼과 일관된 형식·메타데이터가 필요하며, 과제 명세도 선행 패리티를 RS 아닌 것으로 바꾸지 않도록 정했다. 이 변경은 비용 정책이나 Go 와이어 형식을 바꾸지 않았다.
