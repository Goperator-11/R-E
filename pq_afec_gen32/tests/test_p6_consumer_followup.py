"""Pure P6 consumer checks, without report main, rendering, or experiments."""
import ast
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import p6_report as R


def p10_fragment(function_name, p10):
    tree = ast.parse((ROOT / "experiments" / "p6_report.py").read_text(encoding="utf-8"))
    f = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function_name)
    node = next(n for n in f.body if isinstance(n, ast.If)
                and isinstance(n.test, ast.Name) and n.test.id == "p10"
                and any(isinstance(x, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_p10_facts"
                                                         for t in x.targets) for x in n.body))
    lines = []
    ns = dict(p10=p10, A=lines.append, fmt=R.fmt, cell=R.cell,
              p10_test_facts=R.p10_test_facts, check_label=R.check_label)
    exec(compile(ast.Module(body=[copy.deepcopy(node)], type_ignores=[]), "p10_pure_fragment", "exec"), ns)
    return "\n".join(lines)


class P18ConsumerTests(unittest.TestCase):
    def test_new_plugin_preferred_and_legacy_needed_falls_back(self):
        p18 = {"verdict": [{"significant": False, "n_per_arm": 100,
                            "n_plugin_per_arm": 900, "n_needed_per_arm": 12345},
                           {"significant": False, "n_per_arm": 200, "n_needed_per_arm": 1100}]}
        out = R.sample_facts(None, p18)
        self.assertEqual(out["p18_n_plugin"], (900, 1100))
        self.assertEqual(out["p18_n_now"], (100, 200))
        self.assertEqual(out["p18_n_undecided"], 2)

    def test_explicit_new_unknown_is_not_replaced_with_legacy_number(self):
        out = R.sample_facts(None, {"verdict": [{"significant": False,
                               "n_plugin_per_arm": None, "n_needed_per_arm": 100}]})
        self.assertNotIn("p18_n_plugin", out)
        self.assertEqual(out["p18_n_undecided"], 1)

    def test_invalid_plugin_values_do_not_become_sample_requirements(self):
        rows = [{"significant": False, "n_plugin_per_arm": v} for v in (True, float("nan"), float("inf"), -1)]
        out = R.sample_facts(None, {"verdict": rows})
        self.assertNotIn("p18_n_plugin", out)
        self.assertEqual(out["p18_n_plugin_condition_count"], 0)
        self.assertEqual(out["p18_n_undecided"], 4)

    def test_alpha_corrects_legacy_ci95_name_without_inventing_method(self):
        p18 = {"verdict": [{"alpha": .01, "obs_gain_ci95_half": 1,
                            "significant": False, "n_needed_per_arm": 500}]}
        facts = R.sample_facts(None, p18)
        self.assertEqual(facts["p18_confidence_levels"], [.99])
        self.assertEqual(facts["p18_connection_methods"], [])
        text = " ".join(R.p18_consumer_notes(p18))
        self.assertIn("99.00%", text)
        self.assertIn("역사 출력 명칭", text)
        self.assertIn("추가 표본이나 검정력을 보장하지 않는다", text)

    def test_missing_alpha_does_not_assume_95_percent_from_name(self):
        facts = R.sample_facts(None, {"verdict": [{"obs_gain_ci95_half": 1}]})
        self.assertEqual(facts["p18_confidence_levels"], [])

    def test_new_method_cap_coverage_and_unit_scope_are_read(self):
        p18 = {"verdict": [{"connection_ci_method": "normal_iid", "alpha": .01,
                             "family_confidence_level": .95}],
               "current_adaptive_default_m_max": 3,
               "trial_coverage": dict(planned_n=74000, recorded_n=74000, ok_n=73995, failed_n=5, missing_n=0),
               "journal_provenance": dict(reused_units=4, new_units=1, unjournaled_units=1)}
        text = " ".join(R.p18_consumer_notes(p18))
        self.assertIn("상한은 3", text)
        self.assertIn("iid 정규근사", text)
        self.assertIn("전체 명목 신뢰수준은 95.00%", text)
        self.assertIn("재사용 4, 신규 1, 저널 미저장 1", text)
        self.assertIn("성공 73995", text)

    def test_integer_and_json_string_arm_keys_both_supported(self):
        p17 = {"gain": [{"cond": "2Mbps", "allowed_by_loss": {"15": {"means": {"m3": 49, "m2": 50}}}}]}
        for obs in ({3: 49, 2: 50}, {"3": 49, "2": 50}):
            out = R.sample_facts(p17, {"verdict": [{"cond": "2Mbps15", "obs": obs}]})
            self.assertEqual(out["m3m2_p18"], -1)
            self.assertTrue(out["m3m2_same_sign"])


class P20ConsumerTests(unittest.TestCase):
    def test_model_and_same_data_observed_targets_are_distinguished(self):
        d = {"conds": [{"pairs": [{"n_target_source": "model_delta"},
                                  {"n_target_source": "observed_same_data_delta"}, {}]}]}
        text = " ".join(R.p20_consumer_notes(d))
        self.assertIn("모형차 1쌍, 같은 자료 관측차 1쌍, 미기록 1쌍", text)
        self.assertIn("고정된 독립 목표나 검정력 보장이 아니다", text)
        self.assertIn("옛 p20", text)

    def test_input_denominators_and_journal_selection_are_not_called_new_measurement(self):
        d = {"input_coverage": {"complete": False, "expected_conditions": 21, "expected_arms": 78,
             "analysed_conditions": 20, "analysed_arms": 74, "problems": ["missing"],
             "expected": {"condition": {"m1": dict(requested_n=10, recorded_n=9, successful_n=8, failed_n=1)}}},
             "input_provenance": {"p17": {"available": True, "sha256": "input-hash",
                 "journal_selection": {"fingerprint": "fp", "sha256": "journal-hash",
                     "units": [{"run_id": "old-run", "recorded_at": "old-time"}, {"run_id": None}]}}}}
        text = " ".join(R.p20_consumer_notes(d))
        self.assertIn("요청 10, 반환 9, 성공 8, 실패 1", text)
        self.assertIn("계획 조건/팔 21/78, 분석 조건/팔 20/74", text)
        self.assertIn("미기록", text)
        self.assertIn("단위 2개", text)
        self.assertIn("없는 단위 1개", text)
        self.assertIn("input-hash", text)
        self.assertIn("새 실측으로 세지 않는다", text)

    def test_p20_notes_do_not_change_inputs_or_legacy_checks(self):
        d = {"checks": [{"ok": False, "check": "original"}], "conds": [{"pairs": [{}]}]}
        initial = copy.deepcopy(d)
        R.p20_consumer_notes(d)
        self.assertEqual(d, initial)


class P10ConsumerTests(unittest.TestCase):
    def fixture(self):
        return {"results": [{"check": "pass", "ok": True, "kind": "시험"},
                            {"check": "failed", "ok": False, "kind": "시험"},
                            {"check": "effect", "ok": None, "kind": "판정불능", "gating": False,
                             "status": "indeterminate", "detail": "resolution unavailable"},
                            {"check": "diagnostic", "ok": True, "kind": "diagnostic", "counted": False},
                            {"check": "inventory", "ok": False, "kind": "재고"}],
                "tests_passed": 99, "tests_total": 99, "open_gaps": 0}

    def test_new_indeterminate_not_failure_and_legacy_bool_labels_unchanged(self):
        d = self.fixture()
        labels = [R.check_label(r) for r in d["results"][:4]]
        self.assertEqual(labels, ["통과", "미흡", "판정불능", "진단"])
        facts = R.p10_test_facts(d)
        self.assertEqual((facts["passed"], facts["total"]), (1, 2))
        self.assertEqual([r["check"] for r in facts["failed"]], ["failed"])
        self.assertEqual(len(facts["excluded"]), 2)

    def test_old_true_with_indeterminate_kind_remains_indeterminate(self):
        d = {"results": [{"check": "effect", "ok": True, "kind": "판정불능"}]}
        self.assertEqual(R.check_label(d["results"][0]), "판정불능")
        self.assertEqual(R.p10_test_facts(d)["total"], 0)

    def test_markdown_source_branch_preserves_actual_failure_only(self):
        text = p10_fragment("build_markdown", self.fixture())
        self.assertIn("| effect | 판정불능 |", text)
        self.assertIn("| failed | 미흡 |", text)
        self.assertIn("1 / 2 통과", text)
        bad = next(line for line in text.splitlines() if line.startswith("미흡한 항목"))
        self.assertIn("failed", bad)
        self.assertNotIn("effect", bad)

    def test_pdf_source_branch_uses_same_count_and_exclusion(self):
        text = p10_fragment("build_onepager", self.fixture())
        self.assertIn("1 / 2 통과", text)
        self.assertIn("판정불능·진단 2개", text)
        self.assertNotIn("99 / 99", text)

    def test_unknown_null_has_no_invented_boolean_failure(self):
        self.assertEqual(R.check_label({"ok": None}), "판정 없음")
        self.assertEqual(R.p10_test_facts({"results": [{"ok": None}]})["failed"], [])


class DiagnosticAndRulerTests(unittest.TestCase):
    def test_inline_diagnostic_metadata_excluded_without_reclassifying_old_bool_rows(self):
        text = R.late_stage_summary({"test": {"checks": [
            {"check": "legacy", "ok": True}, {"check": "fail", "ok": False},
            {"check": "diag", "ok": True, "counted": False},
            {"check": "diag2", "ok": None, "gating": False}]}})
        self.assertIn("1/2", text)
        self.assertIn("diag2", text)
        self.assertNotIn("2/4", text)

    def test_position_range_is_never_treated_as_ci_width(self):
        out = R.ruler_facts(None, {"gain": [{"pos_effect_ms": 10.0}]})
        self.assertEqual(out["bars"], [])
        self.assertFalse(out["finer"])
        self.assertEqual(out["p17_position_range_ms"], 10.0)
        both = R.ruler_facts({"worst_ci95_half_ms": 2.0}, {"gain": [{"pos_effect_ms": .1}]})
        self.assertTrue(both["finer"])
        self.assertEqual(len(both["bars"]), 1)


if __name__ == "__main__":
    unittest.main()
