from __future__ import annotations

import math

import blockstat as BST

PROTOCOL = "matched-block-windows-v2"


def block_window(blocks, ids, id_key):
    ids = list(ids)
    if (not ids or any(type(i) is not int or i < 0 for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("block window must contain unique explicit IDs")
    by_id = {}
    for block in blocks:
        key = block[id_key]
        if type(key) is not int or key < 0:
            raise ValueError("block IDs must be nonnegative integers")
        if key in by_id:
            raise ValueError("duplicate block ID: %s" % key)
        by_id[key] = block
    selected, values = [], []
    for key in ids:
        if key not in by_id:
            raise ValueError("missing block ID: %s" % key)
        block = by_id[key]
        if (type(block.get("n")) is not int or block["n"] <= 0
                or type(block.get("ok")) is not int
                or not 0 <= block["ok"] <= block["n"]):
            raise ValueError("block %s needs integer attempt/success counts" % key)
        raw = block.get("ms_rows")
        if not isinstance(raw, list) or len(raw) != block.get("n"):
            raise ValueError("block %s needs trial-aligned ms_rows" % key)
        valid = [v for v in raw if v is not None]
        if not valid or any(isinstance(v, bool) or not isinstance(v, (int, float))
                            or not math.isfinite(v) or v < 0 for v in valid):
            raise ValueError("block %s has no valid finite successful samples" % key)
        if block.get("ok") != len(valid):
            raise ValueError("block %s success count mismatch" % key)
        reported = block.get("mean")
        actual = sum(valid) / len(valid)
        if isinstance(reported, bool) or not isinstance(reported, (int, float)) or not math.isclose(
                reported, actual, rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError("block %s mean disagrees with raw samples" % key)
        selected.append(block)
        values.extend(valid)
    return selected, values


def _mean(values):
    return sum(values) / len(values)


def paired_contrast(auto, fixed, alpha=0.05):
    if len(auto) != len(fixed) or len(auto) < 2:
        raise ValueError("paired contrast needs at least two matched blocks")
    if (isinstance(alpha, bool) or not isinstance(alpha, (int, float))
            or not 0 < alpha < 1):
        raise ValueError("alpha must be between zero and one")
    for record in list(auto) + list(fixed):
        value = record.get("mean")
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0):
            raise ValueError("paired contrast needs finite nonnegative means")
    differences = [a["mean"] - b["mean"] for a, b in zip(auto, fixed)]
    mu = _mean(differences)
    se = math.sqrt(sum((v - mu) ** 2 for v in differences)
                   / ((len(differences) - 1) * len(differences)))
    half = BST.t_crit(len(differences) - 1, alpha) * se
    return {"mean_ms": mu, "se_ms": se, "half_ms": half,
            "lower_ms": mu - half, "upper_ms": mu + half,
            "blocks": len(differences), "differences_ms": differences,
            "alpha": alpha}


def matched_diagnostics(auto_blocks, fixed_blocks, selection_ids,
                        evaluation_ids, id_key, family_size=None):
    selection_ids, evaluation_ids = list(selection_ids), list(evaluation_ids)
    if set(selection_ids) & set(evaluation_ids):
        raise ValueError("selection and evaluation blocks overlap")
    if not fixed_blocks:
        raise ValueError("fixed candidate set is empty")
    family_size = len(fixed_blocks) if family_size is None else family_size
    if type(family_size) is not int or family_size < len(fixed_blocks):
        raise ValueError("comparison family cannot omit fixed candidates")
    auto, _ = block_window(auto_blocks, evaluation_ids, id_key)
    selection, evaluation, comparisons = {}, {}, {}
    for arm, blocks in fixed_blocks.items():
        train, _ = block_window(blocks, selection_ids, id_key)
        test, _ = block_window(blocks, evaluation_ids, id_key)
        selection[arm] = _mean([b["mean"] for b in train])
        evaluation[arm] = _mean([b["mean"] for b in test])
        comparisons[arm] = paired_contrast(auto, test, alpha=0.05 / family_size)
    selected = min(selection, key=selection.get)
    observed_best = min(evaluation, key=evaluation.get)
    selected_blocks, _ = block_window(fixed_blocks[selected], evaluation_ids, id_key)
    selected_contrast = paired_contrast(auto, selected_blocks)
    limits = ["Within-run chronological split, not independent confirmation.",
              "Latency is conditional on success; failure counts are retained.",
              "Observed-best contrasts use evaluation data to choose a candidate.",
              "Paired-t intervals assume independent approximately normal block differences.",
              "Bonferroni handles candidate multiplicity, not serial/position effects."]
    upper = max(c["upper_ms"] for c in comparisons.values())
    lower = max(c["lower_ms"] for c in comparisons.values())
    return {"protocol": PROTOCOL, "selection_ids": selection_ids,
            "evaluation_ids": evaluation_ids, "weighting": "equal acquisition blocks",
            "auto_mean_ms": _mean([b["mean"] for b in auto]),
            "fixed_means_ms": evaluation, "selection_means_ms": selection,
            "best_observed": observed_best, "selected_fixed": selected,
            "selected_fixed_contrast": selected_contrast,
            "observed_best_regret_ms": comparisons[observed_best]["mean_ms"],
            "contrasts": comparisons, "family_size": family_size,
            "worst_regret_upper_ms": upper,
            "two_ms_diagnostic": ("within" if upper < 2.0 else
                                  "outside" if lower >= 2.0 else "indeterminate"),
            "independent_confirmation": False, "limitations": limits,
            "counts": {arm: {"attempted": sum(b["n"] for b in rows),
                              "successful": sum(b["ok"] for b in rows)}
                       for arm, rows in [("auto", auto)] +
                       [(a, block_window(b, evaluation_ids, id_key)[0])
                        for a, b in fixed_blocks.items()]}}
