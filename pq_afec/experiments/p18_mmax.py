# -*- coding: utf-8 -*-
"""P18: fixed m=1..4 observations and model comparisons.

The current Python/Go adaptive default cap is 3. The m2-to-m4 contrast is a
fixed-arm counterfactual, not a direct adaptive-cap intervention. Historical
condition labels are retained so old journal keys keep their original meaning.

HCT is conditional on successful trials; failures remain in trial_coverage.
Five primary comparisons use alpha=.05/5. Connection intervals use a normal
approximation, while Latin-square intervals use Student t with block-cell means.
The wider half-width rule and all original performance thresholds are retained.
Each selected half-width is paired with its own estimate. Additive/independent
Latin-square errors and iid connection errors are assumptions, not guarantees.
"""
import copy
from datetime import datetime, timezone
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
import padbed as B
from padfec import policy as POL
from _journal import Journal, code_fingerprint
import blockstat as BST

RTT_MS = 50.0
GROUP = "X25519MLKEM768"
K = 2  # Flush hint; actual first-flight k remains in trial_records.
N_DEFAULT = 250
N_PRECISE = 750
N = int(os.environ.get("PADFEC_P18_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))
ARMS = [1, 2, 3, 4]
CONDS = [
    ("m_max2포기·무손실", 16000, 1.0, 0.0, 0.0, max(40, N // 6)),
    ("임계사이·버스트3", 4032, 3.0, 15.0, 0.0, N * 3),
    ("임계위·무버스트", 9000, 1.0, 15.0, 0.0, N),
    ("임계위·2Mbps", 9000, 1.0, 2.0, 2.0, N),
    ("임계위·2Mbps·손실15", 9000, 1.0, 15.0, 2.0, N),
]


def mean(v):
    return (sum(v) / len(v)) if v else None

def se(v):
    """평균의 표준오차."""
    if not v or len(v) < 2:
        return None
    mu = sum(v) / len(v)
    var = sum((x - mu) ** 2 for x in v) / (len(v) - 1)
    return math.sqrt(var / len(v))

def model_j(cert, L, p, up, m):
    """이 조건에서 m 을 강제했을 때 모형이 말하는 J.

    🩸 2026-08-25 - C 가 `1146` 으로 박혀 있었다. 우리가 재는 그룹은
       X25519MLKEM768 이고 실측 C 는 1448 이다(1146 은 어느 그룹도
       아니다). natural_k 가 1 vs 2 로 갈려 **모형이 k=1 로** 계산했고,
       그래서 m=2->m=4 예측 이득이 +17.27 ms 로 부풀었다. 바른 C 로는
       +2.38 ms 이고 실측 +1.43 ms 가 그 60% 다 - 검사 6 이 잡은 것은
       알고리즘이 아니라 이 상수였다. padbed.measured_C 로 읽는다.
    """
    d = POL.decide_v2(C=B.measured_C(GROUP), cert_bytes=cert,
                      rtt_ms=RTT_MS, p=p / 100.0,
                      burst=L, s0_base=POL.S0_BASE_MLKEM,
                      c_pkt=POL.C_PKT_POLICY_DEFAULT, W=1280,
                      max_steps=2, m_max=max(m, 1), uplink_mbps=up)
    # run_cond fixes IPS at 1280. Padding/combo candidates measure another arm.
    cs = [c["j_ms"] for c in d["candidates"]
          if c["m"] == m and c.get("delta_per_dgram", 0) == 0
          and c.get("W_eff", 1280) == 1280]
    return min(cs) if cs else None

def trial_coverage(rows, conditions, arms):
    """Check the same complete-trial contract used for journal eligibility."""
    expected = {c[0]: c[5] for c in conditions}
    nseg = len(conditions) * len(arms) ** 2
    planned = sum(c[5] * len(arms) ** 2 for c in conditions)
    got = sum(len(r.get("segments") or []) for r in rows)
    recorded = successes = failed = missing = 0
    problems = []
    names = [r.get("cond") for r in rows]
    if len(names) != len(expected) or set(names) != set(expected):
        problems.append("조건 누락·중복 또는 예상하지 않은 조건")
    for r in rows:
        name = r.get("cond")
        n = expected.get(name)
        segments = r.get("segments") or []
        if (r.get("complete") is not True or r.get("err")
                or type(n) is not int or n <= 0
                or r.get("n_per_block") != n
                or len(segments) != len(arms) ** 2):
            problems.append("%s: 조건의 complete 계약 또는 오류 검사 실패" % name)
        for s in segments:
            count, ok = s.get("n"), s.get("ok")
            valid = (type(count) is int and type(ok) is int
                     and count >= 0 and 0 <= ok <= count)
            if valid:
                recorded += count
                successes += ok
                failed += count - ok
                if type(n) is int:
                    missing += max(0, n - count)
            mu = s.get("mean")
            if (not valid or count != n or ok != n or s.get("err")
                    or s.get("planned_n", n) != n
                    or type(mu) not in (int, float) or not math.isfinite(mu)):
                problems.append("%s block%s m%s: 계획 %s, 기록 %s, 성공 %s, 오류 %s"
                                % (name, s.get("block"), s.get("m"), n,
                                   count, ok, s.get("err") or "없음"))
    # Include wholly absent segments/conditions in missing-record accounting.
    missing = max(missing, max(0, planned - recorded))
    return {"planned_n": planned, "recorded_n": recorded, "ok_n": successes,
            "failed_n": failed, "missing_n": missing,
            "planned_segments": nseg, "recorded_segments": got,
            "complete": bool(rows) and got == nseg and not problems,
            "problems": problems,
            "hct_scope": "successful_trials_only"}

def pos_effect(rec):
    """자리별 구간 평균의 범위. 인과적 순서 효과로 해석하지 않는다."""
    by = {}
    for s in rec["segments"]:
        if s["mean"] is not None:
            by.setdefault(s["pos"], []).append(s["mean"])
    v = [mean(x) for x in by.values() if x]
    return (max(v) - min(v)) if len(v) >= 2 else 0.0

def gain_ci(a, b, alpha):
    """Pooled successful-trial difference and normal-iid half-width."""
    sa, sb = se(a), se(b)
    if sa is None or sb is None:
        return None, None
    z = statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)
    return mean(a) - mean(b), z * math.sqrt(sa * sa + sb * sb)


def decision_gain(v):
    """Prefer the estimate belonging to the selected interval; read old data too."""
    if "decision_gain_m2_to_m4" in v:
        return v["decision_gain_m2_to_m4"]
    return v["obs_gain_m2_to_m4"]


def ratio_ok(v):
    pg, og = v["pred_gain_m2_to_m4"], decision_gain(v)
    half = v.get("ci_half_used")
    if not v["significant"] or type(half) not in (int, float):
        return None
    if not math.isfinite(half) or half <= 0 or not pg or abs(pg) < half:
        return None
    return 0.5 <= og / pg <= 2.0


def unit_key(name, cert, L, loss, up, n_conn):
    return "%s|c%d|L%g|l%g|u%g|n%d" % (name, cert, L, loss, up, n_conn)


def attach_unit_provenance(rec, jr, key, *, journaled, started_at=None,
                           finished_at=None):
    """Keep journal values immutable; preserve absent dates in historical units."""
    if journaled:
        unit = jr.provenance([key])["units"][0]
        meta = dict(unit, fingerprint=jr.fingerprint, journaled=True,
                    recording_scope="completed_journal_unit")
    else:
        meta = dict(key=key, fingerprint=jr.fingerprint, run_id=jr.run_id,
                    recorded_at=finished_at, reused=False, journaled=False,
                    recording_scope="result_unit_completed_not_journaled",
                    note="Completion time of the assembled unit, not final file publication.")
    if started_at is not None:
        meta["measurement_started_at"] = started_at
        meta["measurement_finished_at"] = finished_at
    result = dict(rec)
    result["unit_provenance"] = meta
    return result


def result_provenance(rows, jr):
    """Report consumed journal units and new incomplete units separately."""
    units = [copy.deepcopy(r.get("unit_provenance")) for r in rows]
    units = [u for u in units if u is not None]
    return dict(schema_version=1, fingerprint=jr.fingerprint,
                current_run_id=jr.run_id, units=units, used_units=len(units),
                reused_units=sum(u["reused"] for u in units),
                new_units=sum(not u["reused"] for u in units),
                unjournaled_units=sum(not u["journaled"] for u in units),
                unknown_run_id_units=sum(not u.get("run_id") for u in units),
                unknown_recording_time_units=sum(not u.get("recorded_at") for u in units),
                note="Unit recording times are not per-trial timestamps; run IDs are not independent replicates.")



def run_cond(name, cert, L, loss, up, n_conn, jr):
    key = unit_key(name, cert, L, loss, up, n_conn)
    if jr.has(key):
        return attach_unit_provenance(jr.get(key), jr, key, journaled=True)
    started_at = datetime.now(timezone.utc).isoformat()
    acc = {m: [] for m in ARMS}
    seg, err = [], ""
    p, sp = B.start_server(cert, fec="on")
    try:
        # 라틴 방격: 블록마다 순서를 한 칸씩 돌린다 -> 각 팔이 각 자리 1 번
        for blk in range(len(ARMS)):
            B.set_netem(RTT_MS / 2.0, loss_c2s=loss, burst_len=L,
                        rate_up_mbit=up)
            order = ARMS[blk:] + ARMS[:blk]
            for pos, m in enumerate(order):
                # 🩸 2026-08-26 - 대역이 걸리면 gap 을 벌린다. gap 8 ms 로
                # 붙여 돌리면 앞 연결의 *뒤따르는* 패리티가 다음 연결의 첫
                # 비행 뒤에 줄을 서서, m 이 클수록 불리해진다(2 Mbps 에서
                # m3-m2 가 gap 8 이면 +5.11 ms, gap 600 이면 +0.02 ms).
                # 큐를 다음 연결에 떠넘긴 것이지 악수의 비용이 아니다.
                # p17_adaptive_value.py 의 같은 주석과 같은 근거다.
                rows, cs, e = B.run_client(GROUP, n_conn, fec="on", m=m,
                                           gap_ms=(50 if up > 0 else 8),
                                           timeout_s=10,
                                           expect_k=K, uplink_mbps=up)
                if e:
                    err = " | ".join(x for x in (err, "block%d m%d: %s" % (blk, m, e)) if x)
                ok = [x["ms"] for x in rows if x.get("ok")]
                acc[m].extend(ok)
                seg.append({"block": blk, "m": m, "pos": pos,
                            "planned_n": n_conn, "n": len(rows), "ok": len(ok),
                            "fail": len(rows) - len(ok),
                            "missing": max(0, n_conn - len(rows)), "err": e,
                            "mean": mean(ok), "hct_scope": "successful_trials_only",
                            "trial_records": rows,
                            "client_stats": copy.deepcopy(cs),
                            "client_stats_scope": "client_process_segment"})
                print("   %-16s blk%d m=%d(자리%d) 평균 %.2f"
                      % (name, blk, m, pos, mean(ok) or -1), flush=True)
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    rec = {"cond": name, "cert": cert, "burst": L, "loss": loss,
           "uplink": up, "n_per_block": n_conn,
           "arms": {str(m): {"n": len(v), "mean": mean(v),
                             "hct_scope": "successful_trials_only",
                             "p50": B.pctl(v, 0.5), "ms": v}
                    for m, v in acc.items()},
           "segments": seg, "srv_crc_fail": ss.get("recover_crc_fail"),
           "srv_stats_present": bool(ss), "err": err,
           "server_stats": copy.deepcopy(ss),
           "server_stats_scope": "shared_condition_across_fixed_arms_and_blocks",
           "hct_scope": "successful_trials_only"}
    complete = (not err and n_conn > 0 and len(seg) == len(ARMS) ** 2
                and all(s["n"] == s["ok"] == n_conn for s in seg))
    rec["complete"] = complete
    rec["trial_coverage"] = trial_coverage(
        [rec], [(name, cert, L, loss, up, n_conn)], ARMS)
    journaled = not err and complete and bool(ss) and ss.get("recover_crc_fail") == 0
    finished_at = datetime.now(timezone.utc).isoformat()
    if journaled:
        jr.record(key, rec)
    return attach_unit_provenance(rec, jr, key, journaled=journaled,
                                  started_at=started_at, finished_at=finished_at)

def analyse_condition(rec, mdl, alpha):
    am = rec["arms"]
    obs = {m: am[str(m)]["mean"] for m in ARMS}
    pg = mdl[2] - mdl[4] if mdl[2] and mdl[4] else None
    pooled, normal_half = gain_ci(am["2"]["ms"], am["4"]["ms"], alpha)
    cells = [(s["m"], s["pos"]) for s in rec["segments"] if s["mean"] is not None]
    balanced, why = BST.balance(cells)
    an = BST.latin_anova([dict(arm=s["m"], pos=s["pos"], block=s["block"],
                             value=s["mean"]) for s in rec["segments"]
                          if s["mean"] is not None])
    blocked, blocked_half = BST.contrast(an, 2, 4, alpha) if an.get("ok") else (None, None)
    half = max(normal_half or 0.0, blocked_half or 0.0)
    # Keep the historical wider-width rule, but pair it with its own estimand.
    use_latin = blocked_half is not None and blocked_half > (normal_half or 0.0)
    estimate = blocked if use_latin else pooled
    method = "latin_square_t" if use_latin else "normal_iid"
    n_now = min(len(am["2"]["ms"]), len(am["4"]["ms"]))
    n_plugin = (int(math.ceil(n_now * (half / abs(estimate)) ** 2))
                if half and estimate else None)
    interval = lambda center, width: ([center-width, center+width]
                                      if center is not None and width is not None else None)
    return dict(
        cond=rec["cond"], uplink=rec["uplink"], obs=obs, model=mdl,
        pred_gain_m2_to_m4=pg, obs_gain_m2_to_m4=pooled,
        connection_ci_half=normal_half, connection_ci_method="normal_iid",
        connection_ci=interval(pooled, normal_half),
        alpha=alpha, per_comparison_confidence_level=1-alpha,
        family_confidence_level=0.95, multiplicity_method="Bonferroni_primary_conditions",
        confidence_level_scope="nominal_under_model_assumptions_not_guaranteed_selected_interval_coverage",
        n_per_arm=n_now, n_plugin_per_arm=n_plugin,
        n_plugin_scope="inverse_square_same_data_diagnostic_no_power_guarantee",
        design_balanced=bool(balanced), design_note=why,
        blocked_gain_m2_to_m4=blocked, blocked_ci_half=blocked_half,
        blocked_ci=interval(blocked, blocked_half),
        blocked_mse=an.get("mse"), blocked_df_resid=an.get("df_resid"),
        pos_f=an.get("pos_f"), pos_ss_share=an.get("pos_share"),
        decision_gain_m2_to_m4=estimate, decision_ci_method=method,
        ci_half_used=half, decision_ci=interval(estimate, half),
        significant=bool(half > 0 and estimate is not None and abs(estimate) > half),
        pos_effect_ms=pos_effect(rec))


def add_result(out, name, ok, detail, *, counted=True, emit=False):
    entry = dict(check=name, ok=bool(ok) if counted else None, detail=detail,
                 kind="criterion" if counted else "diagnostic", counted=counted)
    out["checks" if counted else "diagnostics"].append(entry)
    if emit:
        label = ("통과" if ok else "실패") if counted else "진단"
        print("[%s] %s %s" % (label, name, detail), flush=True)


def build_result(rows, models, conditions, *, provenance=None, emit=False):
    """Pure assembly for stored-data/mock validation; no I/O or collection."""
    out = dict(schema_version=2, rtt_ms=RTT_MS, group=GROUP, n=N, arms=ARMS,
               rows=rows, verdict=[], checks=[], diagnostics=[],
               current_adaptive_default_m_max=POL.M_MAX_DEFAULT,
               comparison_scope="fixed_m2_vs_m4_not_adaptive_cap_intervention",
               hct_scope="successful_trials_only",
               hct_note="HCT는 성공 시행 조건부이며 실패·누락은 trial_coverage에 별도 집계한다")
    if provenance is not None:
        out["journal_provenance"] = provenance
    alpha = 0.05 / max(1, len(conditions))
    for rec in rows:
        if all(rec["arms"][str(m)]["mean"] is not None for m in ARMS):
            mdl = {m: models[rec["cond"]][m] for m in ARMS}
            out["verdict"].append(analyse_condition(rec, mdl, alpha))
    vs = out["verdict"]
    def add(name, ok, detail, counted=True):
        add_result(out, name, ok, detail, counted=counted, emit=emit)
    coverage = trial_coverage(rows, conditions, ARMS)
    out["trial_coverage"] = coverage
    add("1. 계획 시행의 완전성", coverage["complete"],
        "계획 %d, 기록 %d, 성공 %d, 실패 %d, 누락 %d"
        % tuple(coverage[k] for k in ("planned_n", "recorded_n", "ok_n", "failed_n", "missing_n")))
    add("2. 조건별 서버 통계 존재", bool(rows) and all(r["srv_stats_present"] for r in rows),
        "%d/%d, 연결별 계측 완전성을 뜻하지 않는다"
        % (sum(bool(r["srv_stats_present"]) for r in rows), len(rows)))
    spread = [max(v["obs"].values())-min(v["obs"].values()) for v in vs]
    add("3. 팔 평균의 산포", bool(vs) and min(spread) > 0.5, repr(spread))
    add("4. 라틴 방격의 팔·자리 균형",
        bool(vs) and all(v["design_balanced"] for v in vs),
        "가법·오차 독립성은 별도 가정이다")
    add("4b. 연결 정규 반폭과 방격 t 반폭", None,
        " | ".join("%s: 정규 %.6f, 방격 %s, 개별 명목 수준 %.1f%%"
                   % (v["cond"], v["connection_ci_half"] or 0,
                      v["blocked_ci_half"], 100*v["per_comparison_confidence_level"])
                   for v in vs), counted=False)
    dec = [v for v in vs if v["significant"]]
    und = [v for v in vs if not v["significant"]]
    add("5. 판정 가능한 m2-m4 차의 양의 부호",
        bool(dec) and all(decision_gain(v) > 0 for v in dec),
        " | ".join("%s: %+.6f ± %.6f" % (v["cond"], decision_gain(v), v["ci_half_used"])
                   for v in vs))
    add("5b. 판정불능과 표본 플러그인 진단", None,
        " | ".join("%s: 판정불능, 역제곱 대입값 %s (현재 %d), 추가 표본의 보장 아님"
                   % (v["cond"], v["n_plugin_per_arm"], v["n_per_arm"]) for v in und)
        or "판정불능 조건 없음", counted=False)
    ratios = [(v, ratio_ok(v)) for v in vs]
    judged = [(v, r) for v, r in ratios if r is not None]
    add("6. 적격 차의 모형 대비 점비율 0.5~2",
        bool(judged) and all(r is True for v, r in judged),
        "비율 신뢰구간 검사가 아님, 판정 가능 %d/%d" % (len(judged), len(vs)))
    shaped = [v for v in vs if v["uplink"] > 0]
    shaped_ok = []
    for v in shaped:
        og = v["obs"][1]-v["obs"][2]
        pg = v["model"][1]-v["model"][2] if v["model"][1] else None
        ratio = og/pg if pg and abs(pg)>1e-9 else None
        shaped_ok.append(ratio is not None and og>0 and pg>0 and 0.5<=ratio<=2.0)
    add("6b. 대역 조건 m1-m2의 부호·점비율",
        bool(shaped) and all(shaped_ok),
        "기존 점기준 유지, 신뢰구간에 의한 모형 확증이 아님")
    crc = sum(r["srv_crc_fail"] or 0 for r in rows)
    add("7. 조건별 복구 CRC 실패 0", crc == 0, "총 %d" % crc)
    clean = [r for r in rows if r["loss"] == 0]
    pairs = [(r["arms"]["2"]["mean"], r["arms"]["4"]["mean"]) for r in clean
             if r["arms"]["2"]["mean"] and r["arms"]["4"]["mean"]]
    add("8. 무손실 m2 평균이 1.5RTT 초과",
        bool(pairs) and all(a > 1.5*RTT_MS for a, b in pairs),
        "기존 점기준 유지")
    add("9. 같은 조건의 m4 평균이 1.5RTT 이하",
        bool(pairs) and all(b <= 1.5*RTT_MS for a, b in pairs),
        "기존 점기준 유지")
    out["passed"] = sum(c["ok"] for c in out["checks"])
    out["total"] = len(out["checks"])
    out["diagnostic_count"] = len(out["diagnostics"])
    return out


def main():
    B.harden()
    B.require_root()
    B.setup()
    fp = code_fingerprint(["experiments/p18_mmax.py", "experiments/quicbed/qamp.go",
                           "experiments/padbed.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p18_units.jsonl"), fp)
    rows = [run_cond(*condition, jr) for condition in CONDS]
    models = {r["cond"]: {m: model_j(r["cert"], r["burst"], r["loss"], r["uplink"], m)
                          for m in ARMS} for r in rows}
    out = build_result(rows, models, CONDS, provenance=result_provenance(rows, jr), emit=True)
    fname = ("smoke_" if N < N_DEFAULT else "") + "p18_mmax.json"
    print("%d / %d 통과, 진단 %d개 별도" % (out["passed"], out["total"], out["diagnostic_count"]))
    print("saved: %s" % B.save(fname, out))
    return 0 if out["passed"] == out["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
