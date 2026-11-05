import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import comparison, histogram, numeric, rows, run


def analyze(context):
    data = {}
    summary = {}
    for suffix in ("l0", "l2", "l5"):
        name = f"p31_run1_D_p11_2955_{suffix}_units.jsonl"
        sequence = list(rows(context.load(name), "g3auto"))
        data[suffix] = [row.get("p_mean") for _, _, _, row in sequence]
        summary[suffix] = {"rows": len(sequence), "p_mean": numeric(data[suffix]), "actions": histogram(row.get("action") for _, _, _, row in sequence), "obs_y": histogram(row.get("obs_y") for _, _, _, row in sequence), "obs_updated": histogram(row.get("obs_updated") for _, _, _, row in sequence), "obs_skip": histogram(row.get("obs_skip") for _, _, _, row in sequence)}
    comparisons = {}
    for suffix in ("l2", "l5"):
        left, right = data["l0"], data[suffix]
        different = [{"position": i, "l0": x, suffix: y} for i, (x, y) in enumerate(zip(left, right)) if x != y]
        numeric_pairs = [(x, y) for x, y in zip(left, right) if x is not None and y is not None]
        comparisons[suffix] = {"lengths": [len(left), len(right)], "same_length": len(left) == len(right), "exact_equal_positions": sum(x == y for x, y in zip(left, right)), "max_abs_difference": max((abs(x - y) for x, y in numeric_pairs), default=None), "mismatch_count": len(different) + abs(len(left) - len(right)), "mismatch_examples": different[:20], "expected": comparison(sum(x == y for x, y in zip(left, right)), 1600, "동일 길이 1,600행의 결정 전 전체 정밀도 p_mean을 위치별 대조")}
    return {"item": "A0-1", "data_kind": "measurement_reanalysis", "definition": "같은 fingerprint와 key의 마지막 기록을 채택하고 block, 원래 segment/row 순서로 비교한다. p_mean_after와 m_why는 비교값이 아니다.", "source_scripts": ["verify-A7/journals.py"], "summary": summary, "comparisons": comparisons}


if __name__ == "__main__":
    run(analyze)
