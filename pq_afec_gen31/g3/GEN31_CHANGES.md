gen3.1 변경 기록 (X4, 2026-10-02)

이번 변경은 `C:/dev/pq_afec_gen31`에만 적용했다. gen3의 측정 코드와 기록은 수정하지 않았다. 시험은 작성만 했고, 테스트·빌드·Go·WSL 실행은 하지 않았다. `experiments/results/p21_*`와 `experiments/state/p21_*` 측정 자료는 열지 않았다. 아래 동작은 소스 기준이며 시험 통과 여부는 미확인이다.

gen3 대비 이번 작업에서 바꾼 파일은 다음과 같다. 측정 자료를 제외하고 사본을 만든 과정에서 생긴 차이는 이 목록에 포함하지 않는다.

| 파일 | 변경 내용 |
|---|---|
| [experiments/quicbed/qamp.go](C:/dev/pq_afec_gen31/experiments/quicbed/qamp.go:1510) | 진행 중 송신 작업을 기다린 뒤 출력·송신 합계를 확정한다. |
| [experiments/quicbed/qamp_finalstats_test.go](C:/dev/pq_afec_gen31/experiments/quicbed/qamp_finalstats_test.go:135) | X2의 여섯 시험 항목을 가짜 PacketConn과 채널로 검사한다. 새 파일이다. |
| [experiments/p21_gencompare.py](C:/dev/pq_afec_gen31/experiments/p21_gencompare.py:1314) | 개발 자료 판정 차단, 종료·재보고 봉인 재검사, 블록 앞 빌드 탐지를 추가한다. |
| [tests/test_p21_gencompare.py](C:/dev/pq_afec_gen31/tests/test_p21_gencompare.py:392) | 판정 자격, 봉인·바이너리 변경, 빌드 탐지 회귀시험을 추가한다. |
| `g3/GEN31_CHANGES.md` | 변경 근거, 역사 기록의 정정, 실행할 검증과 한계를 기록한다. 새 파일이다. |

클라이언트 송신 통계는 진행 중인 `WriteTo`가 반환하기 전에 복사될 수 있었다. 이때 서버에 도착한 패리티도 출력 행과 합계에서는 빠질 수 있다. `txFinal` 확인과 `txWG.Add`를 같은 mutex 아래에 두어 종료 확정 후 새 통계 작업이 등록되지 않게 했다. `finalSendStats()`는 이미 등록한 작업이 끝난 뒤 타이머와 남은 버퍼를 정리하고 통계를 복사한다. 남은 버퍼를 강제로 송신하지 않는다. 설계 근거는 [X2.md](C:/dev/codex_handoff/codex_out/X2.md:48)이다.

`runClient`의 HCT 확정 위치와 정책용 `st`, `srvBytes` 관측 시점은 유지했다. `cache.observe`, 피드백 관측, `c3.observe`에는 기존 관측을 전달한다. `tr.Close()`와 `udp.Close()` 뒤에 확정한 통계로 연결별 송신 필드와 송신 합계를 갱신하고 행을 출력한다. 피드백 집계는 기존 스냅숏을 사용한다. `-layout v2`의 패킷 생성과 송신 순서 본문은 유지했다. 바이트 일치는 기존 [v2 골든 시험](C:/dev/pq_afec_gen31/experiments/quicbed/qamp_lead_test.go:96)으로 확인해야 한다.

개발 자료에서 H1~H4의 통과·개선 결론이 나오던 경로를 막았다. `development` 판정에는 "평가 불가"와 이유를 기록하고 기술통계를 남긴다. 종료와 `--report-only`는 전체 봉인과 현재 바이너리를 다시 확인하고 실행 시작 때의 해시와 대조한다. 프로토콜, H 추첨, H 예측표도 검사 대상이다. H3에는 봉인된 예측표 해시와 일치하는 바이트만 사용한다. 저장된 1·2회차 결과를 합칠 때도 두 회차의 시작·종료 증거를 재검사한다. 블록 앞에는 `g3bed.load_processes()` 검사를 추가해 빌드가 보이면 기존 incident 기록과 중단 경로를 따른다. 근거는 [X1.md](C:/dev/codex_handoff/codex_out/X1.md:5)이다.

판정문에 적힌 기존 헤더 버전 `fecVer=2`는 `fecVer=1`로 정정한다. 원문은 [verdict_v3.md:121](C:/dev/codex_handoff/state/evo/verdict_v3.md:121)과 [221행](C:/dev/codex_handoff/state/evo/verdict_v3.md:221)이다. 실제 gen-2 상수는 [qamp.go:480](C:/dev/pq_afec/experiments/quicbed/qamp.go:606)의 `1`이고, gen3.1 파서는 [qamp.go:741](C:/dev/pq_afec_gen31/experiments/quicbed/qamp.go:914)에서 `1`과 `3`을 받는다. `layout v2`라는 이름과 와이어의 `fecVer=1`은 별개다. 기존 판정문과 사본의 `g3/SEAL_*`, `RESULT_*`, `PROTOCOL_*`, `*_predictions.json`은 역사 기록으로 보존한다.

측정이 끝난 뒤 Windows에서 실행할 Python 검증 명령은 다음과 같다.

```powershell
Set-Location 'C:\dev\pq_afec_gen31'
python -m pytest -q tests/test_p21_gencompare.py
```

WSL 검증은 다음 내용을 `C:/dev/pq_afec_gen31/g3/verify_gen31.sh`에 LF로 저장한 뒤 실행한다. 이 스크립트 파일은 이번 작업에서 만들지 않았다. 모듈이 요구하는 Go 버전은 [go.mod:17](C:/dev/pq_afec_gen31/experiments/quicbed/go.mod:17)의 `1.26.6`이다.

```bash
set -euo pipefail
cd /mnt/c/dev/pq_afec_gen31/experiments/quicbed
if [ -d "$HOME/goroot" ]; then
  export GOROOT="$HOME/goroot"
  export PATH="$GOROOT/bin:$PATH"
fi
export GOTOOLCHAIN=local
export GOFLAGS=-mod=readonly
files=(qamp.go policy.go policy3.go pfail_table.go qamp_*_test.go policy_*_test.go policy3*_test.go)
CGO_ENABLED=0 go test -count=1 -v "${files[@]}"
CGO_ENABLED=1 go test -race -count=1 "${files[@]}"
```

```powershell
wsl -d Ubuntu -- bash /mnt/c/dev/pq_afec_gen31/g3/verify_gen31.sh
```

`go test`는 위 파일 목록을 사용한다. 같은 디렉터리의 별도 실행 프로그램까지 함께 컴파일하지 않도록 `go test ./...`는 사용하지 않는다. race 검증에는 WSL의 C 컴파일러가 필요하다. 도구와 의존성의 설치 여부는 이번 작업에서 확인하지 않았다.

남은 위험은 다음과 같다.

- 새 시험과 기존 골든 시험을 실행하지 않아 컴파일, 회귀시험, race 검증 결과는 미확인이다.
- HCT 시험은 실제 정책 관측 함수와 출력 함수를 사용하는 단위시험이다. 실제 QUIC Dial을 대체한 runClient 통합시험은 아니다. [qamp_finalstats_test.go:397](C:/dev/pq_afec_gen31/experiments/quicbed/qamp_finalstats_test.go:397)
- HCT를 확정하는 코드 위치는 같지만 WaitGroup 등록과 종료 대기 비용이 실제 HCT 분포나 다음 연결의 시작 시각에 미치는 영향은 미확인이다.
- `BytesOrig`는 여전히 Initial `WriteTo` 진입 바이트다. 오류나 인위적 drop이 있으면 `bytes_orig + bytes_parity`를 실제 UDP 성공 송신량으로 해석할 수 없다. 전체 패리티와 첫 비행 증폭 예산도 구분해야 한다. [X2.md](C:/dev/codex_handoff/codex_out/X2.md:165)
- 블록 앞 검사는 그 시점에 보이는 빌드를 막는다. 블록 도중 시작했다가 끝난 빌드까지 계속 감시하지 않는다. [X1.md](C:/dev/codex_handoff/codex_out/X1.md:27)
- 파일·바이너리 재검사는 검사 시점의 상태를 확인한다. 검사 사이에 변경됐다가 원복된 이력은 별도 추적이 없으면 알 수 없다. WSL 바이너리에 접근할 수 없는 재보고도 확증 자격을 인정하지 않는다. [p21_gencompare.py:1314](C:/dev/pq_afec_gen31/experiments/p21_gencompare.py:1314)
- 기존 봉인을 보존했으므로 수정된 gen3.1 소스는 gen3의 봉인과 일치하지 않는다. 새 확증 측정에는 별도 프로토콜과 봉인이 필요하다. 기존 기록을 덮어써서 일치시키면 안 된다.
- 측정 경로와 설치 스크립트는 이번 작업 범위에서 바꾸지 않았다. [p21_gencompare.py:32](C:/dev/pq_afec_gen31/experiments/p21_gencompare.py:32)는 `/tmp/padfec_p21`을 사용하고, [build_g3b.sh:25](C:/dev/pq_afec_gen31/experiments/quicbed/build_g3b.sh:25)는 `/tmp/qamp_g3`에 설치한다. gen3.1 실측 전 작업·바이너리 경로를 분리해야 한다. 위 단위시험 명령은 설치 스크립트를 호출하지 않는다.

v3.1 정책 (2026-10-02, 3단계 확증 전)

v3.1 명세와 상수 출처는 `g3/PROTOCOL_stage3.md` 0.5절, Go 이식 규칙은 `g3/policy3_reference.md` 4~7절에 있다. 바뀐 파일은 `padfec3/layout.py`, `learn3.py`, `decide3.py`, `experiments/quicbed/policy3.go`, `policy3_test.go`, `qamp.go`(auto3 관측 호출 한 줄), `experiments/gate_v3_parity.py`, 새 `experiments/quicbed/build_g3c.sh`, `g3/policy3_reference_gen.py`와 재생성한 `g3/policy3_reference.json`(sha256 8c04033e…df3f), `experiments/p21_gencompare.py`와 그 시험이다. 위에 적은 X4 시험은 이후 실행해 통과했다(Go 75개, race 0건, 게이트 PASS).

g3c qamp sha256 6baf2b5235d9906062d524af708ee28f06b2c20fa11c64fbc8bb51bc7f274d9b, srcsha 6284fdcf2d324bae4aee6aef56d7f339aa01c3b267e3aa3225277e7c87b3ade4. `build_g3c.sh`는 `~/quicbed_g3c`에서 빌드하고 `/tmp/qamp_g3/g3c`에 설치한다. `/tmp/qamp_g3/g2`가 없거나 sha가 다르면 동결 g2 사본을 sha 확인 뒤 복사한다(build_g3b.sh와 같은 동작이고 러너가 이것에 기댄다).

`python -m pytest tests/`는 이 사본에서 3개가 실패한다: `test_g3_m1confirm.py::PlanTests::test_importing_does_not_touch_stage0_module`, `test_g3_stage0.py`의 `test_plan_matches_sealed_predictions_and_seal_holds`와 `test_full_flow_runs_the_sealed_plan`. `g3/SEAL_stage0.json`이 v3의 `padfec3/layout.py`를 고정하고 있어서다. 이 시험들은 0단계와 M1' 봉인의 역사 기록을 검사하는 것이고 `C:/dev/pq_afec_gen3`에서는 통과한다. 봉인을 고쳐 맞추지 않고 실패를 그대로 둔다.

`experiments/replay_g3.py`는 `observe3`를 `j_pred` 없이 부르므로 그 재생에서는 감시층이 돌지 않는다(명목 2-RTT 건너뛰기는 돈다). 측정 경로가 아닌 개발 도구다.
