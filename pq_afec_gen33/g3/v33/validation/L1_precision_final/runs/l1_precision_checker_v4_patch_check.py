import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
START = RUNS / "L1_action_pool_precision_v2/runs/01793411802054201900_30757347a916450196348695e2886087.started.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(version):
    path = RUNS / ("l1_precision_artifact_check_" + version + ".py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr == "equal" and node.args and isinstance(node.args[0], ast.BinOp)
             and isinstance(node.args[0].left, ast.Constant) and node.args[0].left.value == "fixed_chunk_budget:"]
    assert len(nodes) == 1
    code = compile(ast.Expression(nodes[0]), str(path), "eval")
    spec = importlib.util.spec_from_file_location("precision_checker_patch_" + version, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return path, module, code


def main():
    out = RUNS / "L1_precision_checker_v4_patch_check.json"
    assert not out.exists()
    original = json.loads(START.read_text(encoding="utf-8"))
    assert type(original["time_budget_seconds"]) is float and original["time_budget_seconds"] == 300.0
    versions = {version: load(version) for version in ("v2", "v4")}
    sources = {str(START): sha(START), str(Path(__file__).resolve()): sha(__file__)}
    sources.update({str(path): sha(path) for path, _, _ in versions.values()})
    cases = []
    for version, budget, expected in (("v2", 300.0, False), ("v4", 300.0, True),
                                      ("v4", 299.0, False), ("v4", 300.5, False),
                                      ("v4", True, False), ("v4", "300", False)):
        _, module, code = versions[version]
        start = copy.deepcopy(original)
        start["time_budget_seconds"] = budget
        audit = module.Audit()
        try:
            eval(code, {"audit": audit, "start": start, "run_id": start["run_id"]})
            passed = True
        except ValueError:
            passed = False
        assert passed == expected
        cases.append({"version": version, "budget": budget, "expected_acceptance": expected, "actual_acceptance": passed})
    checker_path, module, _ = versions["v4"]
    checker_tree = ast.parse(checker_path.read_text(encoding="utf-8"))
    schema_nodes = [node for node in ast.walk(checker_tree) if isinstance(node, ast.Tuple) and len(node.elts) == 2
                    and isinstance(node.elts[0], ast.Constant) and node.elts[0].value == "schema"
                    and isinstance(node.elts[1], ast.Constant) and node.elts[1].value == "padfec.world_oracle/v1"]
    assert len(schema_nodes) == 1
    expected_schema = schema_nodes[0].elts[1].value
    producer = Path(r"C:\dev\pq_afec_gen33\experiments\v33\oracle.py")
    producer_tree = ast.parse(producer.read_text(encoding="utf-8"))
    declared_schema = next(node.value.value for node in producer_tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == "SCHEMA" for target in node.targets))
    assert declared_schema == expected_schema
    plan_path = Path(r"C:\dev\pq_afec_gen33\g3\v33\bench_overlays\L1_precision_v1.json")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    sources.update({str(producer): sha(producer), str(plan_path): sha(plan_path)})
    schemas = []
    for kind in ("mc", "structural"):
        result_path = RUNS / "L1_action_pool_precision_v2/results" / (plan["result_partition"][kind][0] + ".json")
        value = json.loads(result_path.read_text(encoding="utf-8"))
        sources[str(result_path)] = sha(result_path)
        schemas.append((kind, value["schema"], True))
    schemas.append(("incorrect_old_checker_expectation", "padfec.v33.oracle/1", False))
    for kind, actual_schema, expected in schemas:
        try:
            module.Audit().equal("result_schema", actual_schema, expected_schema)
            passed = True
        except ValueError:
            passed = False
        assert passed == expected
        cases.append({"version": "v4", "schema_case": kind, "expected_acceptance": expected, "actual_acceptance": passed})
    for path, expected in sources.items():
        assert sha(path) == expected
    result = {"status": "pass", "cases": cases, "sources_sha256": sources,
              "scope": "Exact budget-check AST expression, frozen producer schema and MC/structural result metadata; no result or checkpoint edits, no performance inspection or MC"}
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "pass", "cases": len(cases), "out": str(out), "sha256": sha(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
