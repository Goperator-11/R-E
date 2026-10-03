# v3.2 development validation

최신 검증은 [2026년 10월 3일 후속 수정](2026-10-03-followup/README.md)에 있다. Python 109개와 하위 검사 367개, Go 101개, vet·race·빌드, WSL 빌더 격리 검사 2개와 Python·Go 90,000단계 대조를 통과했다. 합성 적응 비교도 추가했다. 새 네트워크 성능은 측정하지 않았다.

이 폴더 바로 아래의 첫 검사 로그, verification.json과 sources_sha256.json은 [첫 개발 커밋 d3a9764](https://github.com/Goperator-11/R-E/commit/d3a9764f75ac6b7e2a1891f4154ed806bc8017ec)의 자료로 보존한다. 당시 Python 97개와 하위 검사 293개, Go 94개를 검사한 기록이며 현재 소스의 지문으로 쓰지 않는다. 설명은 [첫 검증 기록](initial-validation.md)에 있다.

v3.1의 H1 통과, H2·H3 실패, H4 적응 기여 미확인 판정은 원래 측정의 판정으로 남는다. 개발 검증이나 정책 자체 모형의 합성 비교로 새 실측 성능을 주장하지 않는다.
