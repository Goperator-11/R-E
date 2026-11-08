# 보고서 HWP 빌드 절차

정오표 2판(`docs/REPORT_ERRATA.md`)을 제출용 HWP에 옮기는 순서와 쪽수 확인, 사람이 할 일, C1 재측정 뒤 바꿀 문구를 적는다. 이 문서를 쓴 2026-11-07에는 gen33 C1 재측정(final_x6s_20261107)이 WSL에서 돌고 있어 HWP 빌드를 하지 않았다. 아래 명령은 빌드 단계에서 그대로 쓴다.

## 빌드 출처

로컬 보존 `C:\Users\scien\OneDrive\Desktop\양식.hwp`(sha256 afc8b777ee171f7b662bef702b8dc4e71ea0b6911cad2be36ab7ed5639d40c80)는 로컬 보존 `C:\hwp_work\rne_final\tools\build_report.py`의 산출물이다. 입력은 `양식_원본.hwp`, `content.py`, `figs2` 그림이다. 이 파일은 같은 폴더의 `out\report.hwp`와 sha256이 같고, `content.py`를 고치지 않고 다시 빌드하면 표 6개의 instance id만 다르다(`engine.make_table`의 `id(rows) & 0xfff`). 손으로 고친 부분은 없다.

HWP 레코드를 직접 치환하지 않는다. 로컬 보존 도구 폴더의 content.py 사본을 고쳐 다시 빌드한다. 행 높이 재계산과 표·그림 레코드는 빌더가 맡는다.

## 명령

저장소 루트에서 돈다. `report_repro/apply_errata.py`와 `report_repro/verify_hwp_output.py`, `report_repro/est_report_pages.py`는 `-I` 없이 돈다. 빌더 사본이 같은 폴더의 `engine`을 import하기 때문이다.

```sh
python -I -B report_repro/check_errata.py
python -I -B report_repro/check_measure_keys.py
python -I -B experiments/v33/devreport.py --check-doc docs/REPORT_ERRATA.md --section "측정 절"
python -B report_repro/apply_errata.py --workdir <작업 폴더> --out <출력 hwp>
python -B report_repro/verify_hwp_output.py <양식.hwp 사본> <출력 hwp> docs/REPORT_ERRATA.md
python -B report_repro/est_report_pages.py <작업 폴더> <임시 출력 hwp> errata_v2
```

`report_repro/apply_errata.py`의 순서는 다음과 같다. 양식.hwp sha256이 위 값과 다르면 멈춘다. 로컬 보존 `C:\hwp_work\rne_final\tools`에서 `build_report.py`, `cfb.py`, `content.py`, `engine.py`를 작업 폴더로 복사하고 원본 폴더에는 쓰지 않는다. `적용`이 `apply`인 행의 old를 AST 문자열 상수에서 정확히 한 번 찾아 new로 바꾼다. 이어 쓴 문자열은 하나로 합쳐 대조하므로 줄 치환으로는 안 된다. 본문 `('p', ...)`의 new에 줄바꿈이 있으면 튜플 여러 개로 나눈다. `report_repro/build_layout.json`대로 Table 3을 '7. 재현성과 무결성' 문단 뒤로 옮기고 그림 폭과 줄 간격을 넣은 뒤 `python -B build_report.py <출력>`을 부른다. 출력 파일이 이미 있거나 양식.hwp와 같은 경로이면 거부한다. 빌더는 인자 없이 돌면 `out\report.hwp`를 덮으므로 늘 출력 경로를 준다.

작업 폴더와 출력은 OneDrive 밖에 둔다. 제안 위치는 로컬 보존 `C:\hwp_work\rne_final\out\report_errata_v2.hwp`이고, 쓰기가 막히면 저장소 밖의 임시 폴더를 쓴다. 검증을 통과하면 Polaris를 닫은 상태에서 로컬 보존 `C:\Users\scien\OneDrive\Desktop\양식_정오표반영.hwp`로 한 번만 복사한다. 양식.hwp는 어느 경우에도 덮지 않는다.

`report_repro/verify_hwp_output.py`는 스트림 비교(Section0, DocInfo, PrvText 밖의 변경이면 실패), 적용 행 new의 존재와 old의 잔존, 금지 표현, 【입력 필요】 2개·【확인 필요】 1개·PaperBanana 2개, 줄표, 표와 그림 레코드의 bit29 대응을 검사한다.

## 빌드 시점

X6S 재측정 결과(MP-7), F09의 참고문헌 대조, F31(X2 등) 실행 여부가 정해진 뒤 2026-11-12 18:00 전에 한 번 빌드한다. 그때까지 재측정 결과가 없으면 아래 "재측정 전" 문구로 빌드하고 그 사실을 이 절에 적는다. X2를 재면 RT-29 new의 "속도를 모르거나 잘못 주는 경우는 재지 않았다"를 결과 문장으로 바꿔야 하므로 F31 여부가 먼저다. 2026-11-12 23:59 뒤에 나온 결과는 저장소 문서에만 넣고 정오표 상태를 '마감 뒤, 보고서에 넣지 않음'으로 적는다.

## 쪽수

결과물은 12쪽을 넘으면 넘은 부분을 평가하지 않는다. 요약문 표는 CTRL 속성 bit0이 1(0x082A2311)이라 쪽을 넘지 못하고 넘치면 뒤가 잘린다. 과정 표는 bit0이 0(0x082A2310)이다. 그래서 요약문 증가를 +125자로 묶었고 계산상 0.996쪽이다.

아래는 `report_repro/est_report_pages.py`로 낸 계산값이다. 이 계산기는 현재 제출본에서 12쪽, 9쪽 아래 빈칸 27.3 mm, 마지막 쪽 여유 33.6 mm를 낸다. 기록된 제출본은 12쪽, 9쪽 빈칸 약 6 cm라 계산기가 약 26 mm 보수적이다.

| 설정 | 계산 쪽수 | 비고 |
|---|---|---|
| 본문·제목 줄 간격 160% | 13쪽 | 마지막 쪽 56.0% |
| Table 3 이동, 제목 130% | 13쪽 | 마지막 쪽 36.3% |
| 본문 155% | 13쪽 | 주의 칸만 넘침, 앞쪽 여유 16.1 mm |
| 본문 150%, 제목 130%, Table 3 이동 | 12쪽 | 여유 6.4 mm |

기본값은 마지막 줄이고 `report_repro/build_layout.json`이 이 값을 담는다. 이 계산은 결과물 +1,690자일 때 했다. RT-19를 반복 실험 값으로 고쳐 지금은 +1,723자이므로 빌드할 때 `report_repro/est_report_pages.py`를 다시 돌린다. 한글에서 13쪽이 나오면 다음 순서로 줄인다.

1. `figure_mm`에서 그림 6장을 모두 135 mm로 둔다. 약 11 mm를 벌고, 그림 안 8 pt 글자가 약 7 pt가 된다.
2. RT-03-8과 RT-25를 뺀다.
3. RT-26과 RT-20의 괄호를 뺀다.
4. Fig. 5 캡션의 Fisher 문장을 지운다.
5. 카드 순서(X1, X9, X6)의 반대로 줄인다. Ⅳ-6 문단의 C1 원인 문장과 무손실 절을 먼저 지운다.

RT-19 문구가 한 줄을 늘리면 1판 문장으로 되돌리고 반복 실험 구절을 빼는 쪽을 먼저 택한다.

## Polaris 확인

이 PC에는 한컴과 함초롬바탕이 없어 Polaris의 쪽수는 대체 글꼴 기준이다. LibreOffice는 HWP 5.0을 읽지 못하고(`soffice --convert-to pdf`가 'source file could not be loaded'), pyhwp의 `hwp5odt`는 RelaxNG 검증에서 실패한다.

1. `Get-Process PWord`로 먼저 본다. 떠 있으면 도현님이 쓰는 중으로 보고 미룬다.
2. 로컬 보존 `Start-Process "C:\Program Files (x86)\Polaris Office\Office\Binary\PolarisOffice.exe" <파일>`로 연다.
3. 로컬 보존 도구 사본 폴더에서 `python -B view2.py <파일 이름 일부> <빈 전용 폴더> 2310 3 20`을 돌린다. x=2310은 13% 배율, 휠 3칸이 약 1쪽이고 `tNN.png`가 상태 표시줄이다. view2는 출력 폴더를 비우므로 전용 폴더를 준다.
4. 저장하지 않고 우리가 띄운 PWord만 닫는다. 업데이트 팝업에 WM_CLOSE를 보내지 않는다.

## 사람이 할 일

- 한글에서 열어 요약문 2쪽, 과정 2쪽, 결과물 12쪽 안인지 본다.
- 【입력 필요】 2칸과 【확인 필요】 1곳을 채운다. 정오표 행이 없고 빌드가 그대로 둔다.
- 연구윤리 체크리스트, 서명, 지도교사 체크리스트를 채운다.
- PDF로 저장한다. 파일 이름은 "강원과학고_AI·정보__ML-KEM 적용 시 전송 성능 개선을 위한 QUIC 기반 적응형 FEC 연구.pdf"다.
- RT-01(AI 활용 문구, D57)과 RT-08(Fig. 3 캡션, D74)은 결정 대기라 적용하지 않았다. 결정이 나면 `적용` 열을 바꾸고 다시 빌드한다.

## 재측정 문구

지금 정오표는 재측정 전 판이다. RT-03-3 끝 문장은 "C1 대기 중 도착한 서버 datagram이 flight 크기 추정에 들어간 것이 원인으로 보인다.", RT-04-14는 "datagram 단위 도착 증거(C1)는 개발 측정에서 큰 인증서 조건은 빨라지고 RTT 200 ms 조건은 느려져 방향이 갈렸다.", RT-04-17 첫 항목은 "C1 대기 구간의 flight 크기 추정을 고친 재측정"이다.

재측정 결과가 나오면 수정 전 값 10.71 ms(6.73~14.69)는 지우지 않는다. RT-03-3 끝 문장만 아래 하나로 바꾼다. {d}, {lo}, {hi}는 새 결과 JSON의 S_rtt200 `v33c1_minus_v33none` primary HCT 평균과 95% 구간이고, 그 키를 `report_repro/measure_keys.json`에 더한다.

| 새 구간 | RT-03-3 끝 문장 |
|---|---|
| 0을 포함 | C1 대기 중 도착한 서버 datagram을 flight 크기 추정에서 뺀 뒤 C1 arm을 다시 잰 개발 측정에서는 차이가 {d} ms({lo}~{hi})로 차이를 확인하지 못하였다. 결과를 본 뒤의 수정이므로 확증이 아니다. |
| 모두 양수 | C1 대기 중 도착한 서버 datagram을 flight 크기 추정에서 뺀 뒤 C1 arm을 다시 잰 개발 측정에서도 {d} ms({lo}~{hi}) 느렸다. |
| 모두 음수 | C1 대기 중 도착한 서버 datagram을 flight 크기 추정에서 뺀 뒤 C1 arm을 다시 잰 개발 측정에서는 {-d} ms({-hi}~{-lo}) 빨랐다. 결과를 본 뒤의 수정이므로 확증이 아니다. |

RT-04-14는 "datagram 단위 도착 증거(C1)는 개발 측정에서 큰 인증서 조건은 빨라졌고 RTT 200 ms 조건은" 뒤에 위 세 경우 순서대로 "추정 수정 뒤 차이를 확인하지 못하였다.", "추정 수정 뒤에도 느렸다.", "추정 수정 뒤 빨라졌으나 결과를 본 뒤의 수정이다." 중 하나를 붙인다. RT-04-17에서는 첫 항목을 뺀다. S_bigcert를 다시 재지 않았으면 그 값은 수정 전 값으로 둔다. none 값은 D41 재생 일치가 유지될 때만 그대로 쓴다. 고친 뒤 `docs/loop_record/final_measure_status.json`의 X6R 상태를 결과와 맞추고 위 세 검사를 다시 돌린다.
