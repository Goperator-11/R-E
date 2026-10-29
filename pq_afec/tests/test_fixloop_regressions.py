"""Offline parser, selection, and retry regressions. No measurement subprocesses."""
import argparse
import contextlib
import io
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
import fixloop as F


P10_LOG = """[미흡] 재고: 서버 -> 클라이언트 방향 보호 없음
[미흡] 재고: 제자리(패딩 자리) 배치 미구현
[미흡] C2 RTT 5 ms - 자에 분해능이 있는가 (여유 >= 3x 흔들림)
[통과] C2 RTT 5 ms - 손실 3% 에서 꼬리 비율이 줄어드는가 판정불능
새 영역 시험 11 / 12 통과 | 미구현·제외 항목 3 건
"""


def classify(text, error="exit 1", seconds=380, status="failed", effective="pending"):
    return F.classify("p10", {"status": status, "error": error, "seconds": seconds},
                      effective, "", text, len(text.encode("utf-8")))


def row(stage, kind):
    return {"stage": stage, "title": stage, "kind": kind, "why": "fixture",
            "fails": [], "prescription": "", "loop2": "pending",
            "finished": "fixture", "seconds": 1}


class ParserTests(unittest.TestCase):
    def test_p10_completed_summary_and_only_measured_failure(self):
        failures, score = F.failed_checks(P10_LOG)
        self.assertEqual(score, (11, 12))
        self.assertEqual(len(failures), 1)
        self.assertTrue(failures[0].startswith("C2 RTT 5 ms"))

    def test_legacy_failure_and_summary(self):
        self.assertEqual(F.failed_checks(" [실패] 1. 비교 실패\n 7 / 10 통과 \n"),
                         (["1. 비교 실패"], (7, 10)))

    def test_english_fail_and_summary_suffix(self):
        self.assertEqual(F.failed_checks("[fail] 1. check\n1/2 통과 | note\n"),
                         (["1. check"], (1, 2)))

    def test_inventory_is_not_a_measured_failure(self):
        failures, score = F.failed_checks("[미흡] 재고 : 범위 밖\n12/12 통과\n")
        self.assertEqual((failures, score), ([], (12, 12)))

    def test_trial_denominator_or_intermediate_text_is_not_completion(self):
        failures, score = F.failed_checks("[통과] 반환 11 / 12 성공\n예상 11/12 통과 가능\n")
        self.assertEqual((failures, score), ([], None))

    def test_completed_p10_is_not_environment_or_interruption(self):
        kind, _, failures, _ = classify(P10_LOG)
        self.assertEqual(kind, "진짜결함")
        self.assertEqual(len(failures), 1)

    def test_completed_precision_failure_remains_precision_failure(self):
        self.assertEqual(classify("[미흡] 신뢰반폭이 기준 이상\n11/12 통과 | 끝\n")[0],
                         "표본부족")

    def test_summary_only_failure_is_not_interruption(self):
        self.assertEqual(classify("새 영역 시험 11 / 12 통과 | 끝\n")[0], "진짜결함")

    def test_completed_report_is_not_reclassified_by_environment_exit(self):
        self.assertEqual(classify(P10_LOG, "exit 3221226091")[0], "진짜결함")

    def test_normal_exit_without_expected_report_is_not_environment_or_interruption(self):
        self.assertEqual(classify("", "exit 0", seconds=.1)[0], "진짜결함")

    def test_full_pass_report_with_failed_record_is_still_diagnosed(self):
        self.assertEqual(classify("12/12 통과\n")[0], "진짜결함")

    def test_real_logoff_without_completion_keeps_environment_category(self):
        self.assertEqual(classify("", "exit 3221226091", seconds=.1)[0], "환경사고")

    def test_incomplete_measurement_without_failure_keeps_interruption_category(self):
        self.assertEqual(classify("조건 3 측정 중\n")[0], "도중에죽음")

    def test_skipped_upstream_is_not_empty_log_environment_failure(self):
        self.assertEqual(classify("", "상류 무효: p10", seconds=0,
                                  status="stale_deps")[0], "안돌았음")

    def test_stale_completed_log_is_not_current_failure(self):
        self.assertEqual(classify(P10_LOG, effective="stale")[0], "안돌았음")


class SelectionTests(unittest.TestCase):
    def test_only_selection(self):
        self.assertEqual(F.round_stage_scope(["--only", "p11", "p14"]), ["p11", "p14"])

    def test_only_exact_selection(self):
        self.assertEqual(F.round_stage_scope(["--only", "p14", "--only-exact"]), ["p14"])

    def test_equals_option_selection(self):
        self.assertEqual(F.round_stage_scope(["--only=p14"]), ["p14"])

    def test_no_only_preserves_whole_status_diagnosis(self):
        self.assertIsNone(F.round_stage_scope(["--force", "p14"]))

    def test_empty_only_matches_loop2_full_resolve_semantics(self):
        self.assertIsNone(F.round_stage_scope(["--only"]))

    def test_actual_order_includes_automatically_selected_hard_ancestor(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "round.txt"
            log.write_text("실행할 단계: build, gate, p14\n", encoding="utf-8")
            self.assertEqual(F.round_stage_scope(["--only", "p14"], log),
                             ["build", "gate", "p14"])

    def test_missing_round_log_falls_back_to_only(self):
        self.assertEqual(F.round_stage_scope(["--only", "p14"], "missing-fixture-log"),
                         ["p14"])

    def test_triage_does_not_read_outside_selected_logs(self):
        stages = [("p10", "old failure", "pending", ""), ("p14", "selected", "done", "")]
        with patch.object(F, "stage_ids", return_value=stages), \
             patch.object(F, "loop2_state", return_value={"stages": {"p14": {"status": "done"}}}), \
             patch.object(F, "read_log", return_value=("12/12 통과\n", 20)) as read:
            rows = F.triage(0, selected=["p14"])
        self.assertEqual([(r["stage"], r["kind"]) for r in rows], [("p14", "통과")])
        read.assert_called_once_with("p14")

    def test_status_honors_forwarded_only_without_taking_lock(self):
        with patch.object(sys, "argv", ["fixloop.py", "--status", "--loop2-arg", "--only", "p14"]), \
             patch.object(F, "triage", return_value=[row("p14", "통과")]) as triage, \
             patch.object(F, "take_lock") as take, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(F.main(), 0)
        triage.assert_called_once_with(selected=["p14"])
        take.assert_not_called()


class RetryTests(unittest.TestCase):
    def run_supervisor(self, outcomes, max_retry=1, only=None, rounds=1, run_results=None):
        args = argparse.Namespace(rounds=rounds, max_env_retry=max_retry,
                                  loop2_arg=["--only"] + (only or ["p14"]))
        with patch.object(F, "fingerprints", return_value={"p14": "fixed"}), \
             patch.object(F, "run_round", side_effect=run_results or [(1, 1, None)] * len(outcomes)) as run, \
             patch.object(F, "triage", side_effect=outcomes) as triage, \
             patch.object(F, "save_triage", side_effect=lambda rows, *rest:
                          {"counts": {k: len(v) for k, v in F.summarise(rows).items()}}), \
             patch.object(F, "journal"), patch.object(signal, "signal"), \
             patch.object(F.subprocess, "Popen", side_effect=AssertionError("No real subprocess")), \
             contextlib.redirect_stdout(io.StringIO()):
            code = F.supervise(args)
        return code, run.call_args_list, triage.call_args_list

    def test_completed_failure_stops_without_environment_retry(self):
        code, runs, _ = self.run_supervisor([[row("p14", "진짜결함")]])
        self.assertEqual((code, len(runs)), (1, 1))

    def test_precision_failure_stops_without_environment_retry(self):
        code, runs, _ = self.run_supervisor([[row("p14", "표본부족")]])
        self.assertEqual((code, len(runs)), (1, 1))

    def test_mixed_completed_failure_and_environment_failure_does_not_retry(self):
        code, runs, _ = self.run_supervisor([[row("p14", "진짜결함"), row("p16", "환경사고")]])
        self.assertEqual((code, len(runs)), (1, 1))

    def test_mixed_precision_failure_and_interruption_does_not_retry(self):
        code, runs, _ = self.run_supervisor([[row("p15", "표본부족"), row("p18", "도중에죽음")]])
        self.assertEqual((code, len(runs)), (1, 1))

    def test_timeout_stops_without_retry_even_with_environment_failure(self):
        code, runs, _ = self.run_supervisor([[row("p14", "시간초과"), row("p16", "환경사고")]])
        self.assertEqual((code, len(runs)), (1, 1))

    def test_environment_retry_is_bounded_and_keeps_original_round_log(self):
        code, runs, _ = self.run_supervisor([[row("p14", "환경사고")]] * 2)
        self.assertEqual((code, len(runs)), (3, 2))
        self.assertEqual([call.kwargs["tag"] for call in runs], ["", "_환경재시도01"])
        self.assertEqual([call.args[0] for call in runs], [1, 1])

    def test_zero_retry_limit_never_relaunches(self):
        code, runs, _ = self.run_supervisor([[row("p14", "도중에죽음")]], max_retry=0)
        self.assertEqual((code, len(runs)), (3, 1))

    def test_successful_environment_retry_can_finish(self):
        code, runs, _ = self.run_supervisor([[row("p14", "환경사고")], [row("p14", "통과")]])
        self.assertEqual((code, len(runs)), (0, 2))

    def test_actual_selection_is_passed_to_triage_not_global_diagnosis(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "round.txt"
            log.write_text("실행할 단계: p14\n", encoding="utf-8")
            code, runs, triages = self.run_supervisor([[row("p14", "통과")]],
                                                     run_results=[(0, 1, log)])
        self.assertEqual((code, len(runs)), (0, 1))
        self.assertEqual(triages[0].kwargs["selected"], ["p14"])

    def test_selected_failure_stops_even_when_rounds_allow_more_runs(self):
        code, runs, _ = self.run_supervisor([[row("p14", "진짜결함")]], rounds=4)
        self.assertEqual((code, len(runs)), (1, 1))

    def test_log_retry_followup_does_not_expand_scope(self):
        code, runs, triages = self.run_supervisor([[row("p14", "로그깨짐")], [row("p14", "통과")]])
        self.assertEqual((code, len(runs)), (0, 2))
        self.assertEqual([call.kwargs["selected"] for call in triages], [["p14"], ["p14"]])
        self.assertEqual(runs[1].kwargs["tag"], "_재실행_p14")

    def test_still_broken_log_after_single_followup_is_not_success(self):
        code, runs, _ = self.run_supervisor([[row("p14", "로그깨짐")]] * 2)
        self.assertEqual((code, len(runs)), (1, 2))

    def test_completion_failure_after_log_followup_is_not_remeasured(self):
        code, runs, _ = self.run_supervisor([[row("p14", "로그깨짐")], [row("p14", "표본부족")]])
        self.assertEqual((code, len(runs)), (1, 2))


if __name__ == "__main__":
    unittest.main()
