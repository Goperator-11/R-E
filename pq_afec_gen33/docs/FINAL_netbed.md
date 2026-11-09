# gen33 개발 측정의 netem 환경

F21의 [netbed.py](../experiments/v33/lib/netbed.py)는 개발 측정용 veth와 netem을 구성한다. 기존 [padbed.py](../experiments/padbed.py)의 live 차단은 유지한다. 새 경로는 g3bed의 바이너리 경로나 연결 수집 함수를 사용하지 않는다. QUIC 연결 실행과 결과 판정은 후속 러너가 맡는다.

## 격리와 링크

gen33 저장소 루트에서 실행한다.

```powershell
wsl -d Ubuntu --exec unshare -Urnm python3 -I -B experiments/v33/lib/netbed.py --selftest
```

live 명령 전에 euid 0, 단일 root UID 매핑, 현재 user namespace가 소유한 mount·network namespace를 확인한다. namespace 소유자는 Linux `NS_GET_USERNS`로 얻은 fd와 현재 user namespace의 장치·inode를 비교한다. 조회 실패도 실행 거부다. 이 방식은 /proc/1/ns를 읽을 수 없는 WSL에서도 부분 격리를 구분한다. [Linux 소유 namespace API](https://man7.org/linux/man-pages/man2/ns_get_userns.2const.html)

`setup()`은 /run에 tmpfs를 mount한 뒤 /run/netns를 만들고, v0와 peer namespace의 v1을 연결한다. tmpfs mount 실패는 즉시 전파한다. 양쪽 주소는 각각 10.9.0.1과 10.9.0.2, 기본 MTU는 1500이다. 양쪽 static ARP를 permanent로 등록하고 실제 MTU와 v1의 namespace 분리를 검사한다. 기존 러너의 임시 바이너리·작업 디렉터리는 만들지 않는다.

CPU는 padbed의 `_cpu_list()` 규칙대로 허용 목록을 정렬한 앞 네 개를 고른다. `setup()`을 호출한 스레드에 `sched_setaffinity`를 적용하고 실제 mask를 다시 읽는다. 그 스레드에서 실행한 자식은 mask를 상속한다. 후속 러너는 같은 스레드에서 qamp를 실행하거나, CPU 고정 뒤 실행 스레드를 만들어야 한다. 이미 존재하던 다른 스레드의 affinity까지 바뀌지는 않는다. [Linux CPU affinity API](https://man7.org/linux/man-pages/man2/sched_setaffinity.2.html)

## netem 저널과 바이너리

`set_netem(one_way_ms, loss_c2s, loss_s2c, burst_len, rate_up_mbit, rate_down_mbit, journal=...)`은 양방향 설정을 독립적으로 전달한다. `_netem_spec()`은 기존 padbed의 함수를 그대로 가져온다. delay는 각 방향의 지연이고 rate 0은 제한을 걸지 않는 값이다.

필수 `journal` callback은 설정 뒤 양쪽 `tc qdisc show`의 명령, stdout, stderr, 종료 코드와 요청값을 받는다. 실제 root netem 응답이 없으면 실패한다. callback 실패도 caller로 전파한다. F22 러너는 이 callback으로 실행 저널에 기록을 저장한 뒤 측정 단위를 시작한다. callback을 메모리 목록에 연결한 단위시험과 영속 저널 저장은 구분한다. selftest는 같은 event를 stdout에 JSON으로 남긴다.

`require_bin(path)`는 gen33 전용이다. [gate_v3_parity.py](../experiments/gate_v3_parity.py)의 `binary_report()`를 통해 실제 SHA-256, sidecar SHA-256, srcsha와 `quicbed_fingerprint()`를 비교한다. 파일을 복사하거나 빌드하지 않는다. 동결 gen-2·g3c 팔은 F22에서 계획에 등록한 세대별 해시를 검사해야 한다.

## 확인 범위

2026-11-06의 selftest는 양방향 `delay 25ms loss 2% rate 2Mbit`를 출력하고 종료 코드 0으로 끝났다. CPU mask는 0·1·2·3, 실제 MTU는 양쪽 1500이었다. 설치 바이너리 SHA-256은 `63854e33ac2a33531f3463c72d31899a5f7df5642910497e8ac94ccec308c63a`, srcsha는 `8e3c09609184de9062072019736c90fd174d91092568e4532c94e1a3e236033d`로 현재 소스 지문과 일치했다.

추가 WSL 검사는 일반 사용자 실행과 `-Ur`, `-Urn`, `-Urm` 실행을 모두 종료 코드 2로 거부했다. 정상 격리 안에서는 자식 CPU mask 상속, 양쪽 permanent ARP, c2s의 loss 2%·rate 2Mbit와 s2c의 loss 5%·rate 7Mbit를 확인했다. 검사 전후 host의 링크, qdisc, /run mount와 namespace 목록은 같았다.

실행·집계 스크립트와 로그는 로컬 보존 폴더 `C:/dev/codex_handoff/final/runs/`의 `F21_verify.py`, `F21_wsl_boundaries.py`, `F21_selftest.log`, `F21_wsl_boundaries.log`, `F21_summary.json`에 있다. 단위시험은 [test_v33_netbed.py](../tests/test_v33_netbed.py), 기존 차단 시험은 [test_gen33_runner_isolation.py](../tests/test_gen33_runner_isolation.py)다. 이 검사는 환경 구성과 실패 경계를 확인했으며 QUIC 성능 측정이나 확증 결과는 없다. 실제 smoke는 F26에서 확인한다.
