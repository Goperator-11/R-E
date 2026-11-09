# L2 후보 보류

L2의 EPS 적응 후보는 활성 정책에 채택하지 않았다. 사전 계획의 none·c1 전후 30셀 중 none B8_j10이 미확정이었다. 차이는-1.568806 ms/연결, 조정상한 1.721694로 0.5 비열등 관문을 충족하지 못했다. none B8_j20의 비용 감소로 이를 상쇄하지 않는다.

활성 정책은 L1 커밋 d845395c7e26637c853c76377139ed46b73907e0의 상태 4와 동일하다. 후보 상태 5와 고정 EPS 대조는 g3/v33/policy_snapshots에 보존했다. 후보 전용 시험은 experiments/v33/candidate_tests에 두고 tests/test_v33_l2_candidate.py가 별도 프로세스에서 실행한다. 이후 활성 정책을 고쳐도 후보 증거의 구현을 바꾸지 않는다.

L2는 blocked이며 L3는 활성 L1에서 진행한다. J2·O3 뒤 E7에서 EPS 식별을 다시 검토한다. 전체 수치와 범위는 g3/v33/validation/L2_final_analysis_v1/runs/L2_disposition.md와 L2_findings_v3.md에 보존한다. 과거 라벨 6777행의 누락 2R 0과 2%층 오탐 0은 통과했지만 EPS 적응의 채택 근거로 대신 쓰지 않는다.
