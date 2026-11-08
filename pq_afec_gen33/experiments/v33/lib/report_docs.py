from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re


_LIMITS = (
    ("X4", "토큰·resumption 기준선(X4)"),
    ("X2", "업링크 오입력(X2)"),
    ("X3", "A_pre와 PTO 배수 탐침(X3)"),
    ("X5", "s2c 손실(X5)"),
    ("X7", "다른 QUIC 스택(X7)"),
    ("X8", "initial congestion window 10(X8)"),
    ("E24", "시간 상관 손실(E24)"),
    ("dup", "중복 전송 기준선(dup)"),
    ("k-inflate", "first flight 부풀리기(k-inflate)"),
    ("band_initial", "서버 first flight 7.7~9.0 KB 띠와 Initial 확대 팔"),
    ("H_c6000", "H c6000"),
    ("D_p15_4032", "D_p15_4032"),
    ("TTLB7800", "7.8 kB 응답 TTLB"),
)
_NUMBER = re.compile(r"(?<![A-Za-z0-9_.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\d]|\.\d)")
_IDENTIFIER = re.compile(r"(?<![\w])(?:v\d+(?:\.\d+)+(?:-dev)?|X25519(?:MLKEM768)?|ML-(?:KEM|DSA)(?:-\d+)?|(?:RT|RFC|FIPS)[ -]\d+|[HCLXFME]\d+|gen-?\d+|p\d+|\d+-RTT)(?![\w])")
_EVIDENCE = re.compile(r"(g3/v33/results/[A-Za-z0-9_.-]+\.json)(?:#|\s+)((?:\$\.?)?(?:[A-Za-z_][A-Za-z0-9_.\-]*(?:\[[^\]\n]+\])?)+(?:\.[A-Za-z0-9_.\-]+|\[[^\]\n]+\])*|/[^\s;`]+)")


MEASURED_PLAN_SHA256 = frozenset({"74f58fbb6b0db5c30ef9abf0698ae13dd6bede861bef3215646e5ca3232154b6"})
_SELECTED_COLUMNS = {"측정 뒤 문구": "측정 뒤 문구", "measured": "측정 뒤 문구", "측정 못 한 경우 문구": "측정 못 한 경우 문구",
                     "측정 못 함": "측정 못 한 경우 문구", "러너 구현 뒤 미측정 문구": "러너 구현 뒤 미측정 문구", "구현하였으나": "러너 구현 뒤 미측정 문구"}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _format(value):
    if value is None:
        return "미확인"
    if type(value) is bool:
        return "true" if value else "false"
    if _finite(value):
        return format(value, ".6f").rstrip("0").rstrip(".") if not float(value).is_integer() else str(int(value))
    return str(value).replace("|", "\\|").replace("\n", " ")


def _interval(value):
    if value is None:
        return "미확인"
    if not isinstance(value, (list, tuple)) or len(value) != 2 or not all(_finite(item) for item in value):
        raise ValueError("문서 구간에는 유한수 두 개가 필요하다")
    if value[0] > value[1]:
        raise ValueError("문서 구간의 상하한이 뒤바뀌었다")
    return "[" + ", ".join(map(_format, value)) + "]"


def _table(lines, headers, rows):
    if not rows:
        return
    lines.extend(["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"])
    lines.extend("| " + " | ".join(_format(value) for value in row) + " |" for row in rows)
    lines.append("")


def _m1_data(result):
    data = result.get("m1_result")
    if data is None and result.get("task") == "M1":
        data = result
    if not isinstance(data, dict):
        return {}
    statistics = data.get("statistics", {})
    return {"contrasts": data.get("contrasts", statistics.get("contrasts", {})),
            "a_vs_sealed": data.get("a_vs_sealed", statistics.get("a_vs_sealed", {}))}


def _outside(contrast):
    interval = contrast.get("ci95") if isinstance(contrast, dict) else None
    if interval is None:
        return False
    _interval(interval)
    return interval[0] < -5 or interval[1] > 5


def _header(result):
    task, conditions = result["task"], result["conditions"]
    direction = conditions["loss_direction"]
    if direction == "c2s_only_except_X9_both":
        direction = "c2s 및 양방향을 구분" if task == "X9" else "c2s만"
    uplink = ("정책 입력 uplink는 팔마다 계획에 고정한 값이며 netem 대역은 바꾸지 않음"
              if result.get("policy_uplink_inputs") else "정책 입력 uplink는 netem 대역과 같음")
    paragraph = (f"quic-go {conditions['quic_go_version']} 테스트베드 한 곳, 합성 인증서, "
                 f"W {_format(conditions['w_base_bytes'])}, 손실은 {direction}, "
                 f"initial congestion window {_format(conditions['initial_congestion_window_packets'])} packet, "
                 f"{uplink}. development 측정이며 확증이 아니다.")
    if result.get("exploratory") is True:
        paragraph += f" 이전 결과를 본 뒤 선커밋한 탐색 계획 {result['plan_id']}의 측정이다."
    if task in {"X1", "X6"}:
        paragraph += " 모든 팔을 같은 gen33 서버에 붙였고 봉인 측정의 세대별 서버와 다르다."
    m1 = _m1_data(result)
    contrasts = m1.get("contrasts", {})
    if task == "X6" and any(_outside(contrasts.get(name)) for name in ("a_b", "e_f")):
        paragraph += " 봉인 측정과 직접 비교 불가. 아래 표는 이 실행의 팔 간 비교다."
    delta = m1.get("a_vs_sealed", {}).get("delta_ms")
    if task in {"M1", "X1", "X6", "X9"} and _finite(delta) and abs(delta) > 5:
        paragraph += " 봉인 환경과 표류가 있다."
    if task in {"X1", "X6"} and _outside(contrasts.get("c_d")):
        paragraph += " 자 표류 큼. M1에서 계산한 A/A 자를 그대로 적용했다."
    return paragraph


def _arm_rows(statistics):
    rows = []
    for cell in statistics.get("cells", []):
        for arm in cell.get("arms", []):
            for key, scope in (("primary", "주 분석"), ("all", "번인 포함 전체"),
                               ("burnin", "번인")):
                value = arm.get(key)
                if not value or not value.get("n_rows"):
                    continue
                hct = value.get("hct", {})
                rows.append((cell["cell"], arm["arm"], scope, value.get("n_rows"), hct.get("mean"),
                             _interval(hct.get("ci95")), value.get("success_hct_mean_ms"),
                             value.get("failure_rate"), value.get("one_rtt_rate")))
            for loss in arm.get("by_loss", []):
                for key, scope in (("all", "층 전체"), ("primary", "층 주 분석")):
                    value = loss.get(key)
                    if not value or not value.get("n_rows"):
                        continue
                    hct = value.get("hct", {})
                    name = (f"{scope} c2s={_format(loss.get('loss_c2s_pct'))}% "
                            f"s2c={_format(loss.get('loss_s2c_pct'))}%")
                    rows.append((cell["cell"], arm["arm"], name, value.get("n_rows"), hct.get("mean"),
                                 _interval(hct.get("ci95")), value.get("success_hct_mean_ms"),
                                 value.get("failure_rate"), value.get("one_rtt_rate")))
    return rows


def _cost_rows(statistics):
    rows = []
    for cell in statistics.get("cells", []):
        for arm in cell.get("arms", []):
            for key, scope in (("primary", "주 분석"), ("all", "번인 포함 전체"),
                               ("burnin", "번인")):
                value = arm.get(key)
                if not value or not value.get("n_rows"):
                    continue
                cost = value.get("server_cost", {})
                rows.append((cell["cell"], arm["arm"], scope, cost.get("bytes_in"),
                             cost.get("n_rows"), cost.get("bytes_per_conn"), cost.get("source"),
                             cost.get("status"), value.get("first_flight_bytes_mean"),
                             value.get("first_flight_parity_bytes_mean"),
                             value.get("first_flight_extra_bytes_mean")))
    return rows


def _contrast_rows(statistics, empty=None):
    rows = []
    for cell in statistics.get("cells", []):
        for contrast in cell.get("contrasts", []):
            hct = contrast.get("hct", {})
            aa = contrast.get("aa", {})
            aa_label = ("A/A 적용" if aa.get("applies") else "A/A 없음") if isinstance(aa, dict) else aa
            rows.append((cell["cell"], contrast.get("id"), contrast.get("x"), contrast.get("y"),
                         contrast.get("scope"), hct.get("mean"), _interval(hct.get("ci95")),
                         hct.get("n"), hct.get("df"), aa_label,
                         (aa.get("ruler_ms") if aa.get("ruler_ms") is not None else empty) if isinstance(aa, dict) else None,
                         (aa.get("note") if aa.get("note") is not None else empty) if isinstance(aa, dict) else None,
                         contrast.get("inference_status")))
    if not rows:
        for name, contrast in sorted(statistics.get("contrasts", {}).items()):
            rows.append(("M1", name, name.split("_")[0], name.split("_")[-1], "짝 블록",
                         contrast.get("mean"), _interval(contrast.get("ci95")),
                         contrast.get("n_blocks"), contrast.get("df"),
                         "A/A" if name == "c_d" else "해당 없음",
                         statistics.get("aa", {}).get("ruler_ms") if name == "c_d" else empty,
                         empty, contrast.get("status")))
    return rows


def _reweighted_rows(statistics):
    rows = []
    for cell in statistics.get("cells", []):
        for arm in cell.get("arms", []):
            value = arm.get("reweighted_1_1")
            if value is None:
                continue
            hct = value["hct"]
            rows.append((cell["cell"], arm["arm"], hct.get("mean"), _interval(hct.get("ci95")),
                         hct.get("n"), hct.get("df"), value.get("aa")))
    return rows


def _secondary_contrast_rows(statistics):
    rows = []
    for cell in statistics.get("cells", []):
        for contrast in cell.get("contrasts", []):
            if not any(key in contrast for key in ("one_rtt_difference", "server_bytes_in_per_conn_difference")):
                continue
            rate = contrast.get("one_rtt_difference", {})
            cost = contrast.get("server_bytes_in_per_conn_difference", {})
            rows.append((cell["cell"], contrast.get("id"), contrast.get("x"), contrast.get("y"),
                         contrast.get("scope"), rate.get("mean"), _interval(rate.get("ci95")),
                         cost.get("mean"), _interval(cost.get("ci95"))))
    return rows


def _first_flight_difference_rows(statistics):
    rows = []
    for cell in statistics.get("cells", []):
        for contrast in cell.get("contrasts", []):
            value = contrast.get("first_flight_difference")
            if value is None:
                continue
            missing = value.get("missing_rows", {})
            rows.append((cell["cell"], contrast.get("id"), contrast.get("x"), contrast.get("y"),
                         value.get("scope"), value.get("original_bytes"), value.get("extra_bytes"),
                         value.get("total_bytes"), missing.get("x"), missing.get("y")))
    return rows


def _policy_input_rows(result):
    return [(row.get("cell"), row.get("arm"), row.get("policy_uplink_mbps"), row.get("netem_uplink_mbps"),
             "참값" if row.get("policy_uplink_mbps") == row.get("netem_uplink_mbps") else "오입력")
            for row in result.get("policy_uplink_inputs") or []]


def _x2_rows(statistics):
    rows = []
    for cell in statistics.get("cells", []):
        for contrast in cell.get("contrasts", []):
            if "input_mbps" not in contrast:
                continue
            hct = contrast.get("hct", {})
            rows.append((cell["cell"], contrast.get("id"), contrast.get("input_mbps"), contrast.get("true_mbps"),
                         contrast.get("kind"), hct.get("mean"), _interval(hct.get("ci95")),
                         contrast.get("n_pairs"), hct.get("df"), contrast.get("inference_status")))
    return rows


def _observation_groups(observations):
    values = observations.get("cells", observations.get("groups", [])) if isinstance(observations, dict) else observations
    return values if isinstance(values, list) else []


def _observation_rows(observations):
    rows = []
    for group in _observation_groups(observations):
        scopes = [("전체", group.get("all", group.get("overall", group)))]
        for name, key in (("번인 뒤", "post_burnin"), ("번인", "burnin")):
            if key in group:
                scopes.append((name, group[key]))
        for value in group.get("by_loss", []):
            scopes.append((f"c2s={_format(value.get('loss_c2s_pct'))}% s2c={_format(value.get('loss_s2c_pct'))}%", value))
        scopes.extend(sorted(group.get("by_one_rtt", {}).items(), key=lambda item: (item[0] != "one_rtt", item[0])))
        for name, overall in scopes:
            rows.append((group.get("cell"), group.get("arm"), name,
                         overall.get("valid_rtt", {}).get("valid_rtt_rate"),
                         overall.get("mean_idle_ms"), overall.get("idle_status", "미확인"),
                         overall.get("mean_wait_plus_gap_ms"), overall.get("c1_path_excluded")))
    return rows


def _feedback_rows(observations):
    rows = []
    for group in _observation_groups(observations):
        for name, values in sorted(group.get("feedback_received_rate_by_class", {}).items(),
                                   key=lambda item: (item[0] != "one_rtt", item[0])):
            if values.get("status") == "해당 없음":
                continue
            rows.append((group.get("cell"), group.get("arm"), name, values.get("n"),
                         values.get("received"), values.get("missing"), values.get("rate"),
                         values.get("status"), group.get("c1_path_excluded")))
    return rows


def _pto_tables(lines, statistics):
    rows, contrasts = [], []
    for cell in statistics.get("cells", []):
        for arm in cell.get("arms", []):
            pto = arm.get("primary", {}).get("pto", {})
            for key, label in (("primary", "주 정의"), ("auxiliary", "보조 정의")):
                values = pto.get(key, {})
                rate = values.get("rate")
                rows.append((cell["cell"], arm["arm"], label, values.get("events"),
                             values.get("n_total"), values.get("n_valid"), values.get("missing"),
                             values.get("scope_invalid"), 100 * rate if _finite(rate) else None, pto.get("definition_mismatch"),
                             pto.get("definition_comparable")))
        for key, label in (("primary", "주 정의"), ("auxiliary", "보조 정의")):
            value = cell.get("pto_contrast", {}).get(key, {})
            mean, interval = value.get("mean"), value.get("ci95")
            contrasts.append((cell["cell"], label, 100 * mean if _finite(mean) else None,
                              _interval([100 * item for item in interval]) if interval else "미확인",
                              value.get("n_blocks"), value.get("missing_blocks"), value.get("df")))
    lines.extend(["## PTO 사건", "", "주 정의는 observation.pto_count가 양수인 연결이다. "
                  "count_scope=qlog_loss_timer_expired_lower_bound는 메모리 qlog에 기록된 timer 만료 횟수의 하한이다. "
                  "tracer가 비활성이거나 관측 범위가 맞지 않으면 누락으로 처리한다. "
                  "보조 정의는 initial_datagrams가 first_flight_datagrams보다 둘 이상 많은 연결이다. "
                  "두 정의의 누락과 불일치를 따로 남겼다.", ""])
    _table(lines, ["방향 셀", "팔", "정의", "사건 수", "분석 행 수", "유효 분모", "누락", "관측 범위 불일치", "비율(%)",
                   "정의 불일치", "정의 비교 가능 수"], rows)
    _table(lines, ["방향 셀", "정의", "MLKEM-x25519 차이(%p)", "95% 구간(%p)",
                   "짝 블록 수", "누락 블록", "자유도"], contrasts)
    lines.extend(["PTO 비율 차이의 구간은 짝 블록에서 계산했다. 구간이 영을 포함하면 차이를 확인하지 못한 것으로 읽는다. "
                  "계획용 검정력 근사는 실제 검정력이 아니며 블록 상관과 탈락을 반영하지 않았다.", ""])


def _limits(result):
    measured = set()
    for item in result.get("measured_items", []):
        if (isinstance(item, dict) and _finite(item.get("n_rows")) and item["n_rows"] > 0
                and item.get("execution_status") not in {"자료 없음", "skipped", "not_run", None}):
            measured.add(item.get("id"))
    values = [text for name, text in _LIMITS if name not in measured]
    return ", ".join(values) + "는 재지 않았다." if values else ""


def render_document(result):
    if result.get("label") != "development" or result.get("confirmatory") is not False:
        raise ValueError("결과 문서는 development이며 confirmatory=false여야 한다")
    statistics = result.get("statistics", {})
    lines = [f"# {result['task']} 개발 측정 결과", "", _header(result), ""]
    lines.append(f"실행 ID는 {_format(result['run_id'])}, 정책 판본은 {_format(result['policy_version'])}다.")
    if result.get("result_source"):
        lines.append("결과 근거: `" + result["result_source"] + "`.")
    lines.extend(["", "## 실행과 판정", ""])
    _table(lines, ["항목", "상태"], sorted(result.get("checks", {}).items()))
    lines.extend([f"실행 상태: {_format(result.get('execution_status'))}. "
                  f"통계 판정: {_format(result.get('status', statistics.get('inference_status')))}.", ""])
    if inputs := _policy_input_rows(result):
        lines.extend(["## 정책 uplink 입력", "",
                      "-uplink-mbps로 준 정책 입력과 셀의 netem 대역이다. 두 값이 다른 팔이 오입력 팔이다.", ""])
        _table(lines, ["셀", "팔", "정책 입력(Mbps)", "netem 대역(Mbps)", "입력 종류"], inputs)
    lines.extend(["## HCT와 연결 비율", ""])
    _table(lines, ["셀", "팔", "범위", "행 수", "HCT 평균(ms)", "HCT 95% 구간(ms)",
                   "성공 HCT 평균(ms)", "실패 비율", "1-RTT 비율"], _arm_rows(statistics))
    if reweighted := _reweighted_rows(statistics):
        lines.extend(["번인 뒤 손실 층을 같은 비중으로 재계산한 값은 다음과 같다.", ""])
        _table(lines, ["셀", "팔", "1:1 HCT 평균(ms)", "95% 구간(ms)", "독립 표본 수", "자유도", "A/A"], reweighted)
    lines.extend(["## 서버 계수 비용", "",
                  "서버 수신량은 연결 전체의 bytes_in을 같은 범위의 클라이언트 행 수로 나눈다. "
                  "손실 조건에서도 이 값은 서버 수신량이다. first flight 바이트는 별도 클라이언트 진단이다.", ""])
    _table(lines, ["셀", "팔", "범위", "서버 계수 bytes_in(B)", "분모 행 수", "서버 수신량(B/연결)",
                   "원천", "상태", "first flight 원본 평균(B)", "first flight parity 평균(B)",
                   "first flight extra 평균(B)"], _cost_rows(statistics))
    lines.extend(["g2auto의 클라이언트 parity 계수에는 client_parity_count_unreliable 표지를 둔다. "
                  "클라이언트 bytes_parity와 parity_sent는 비용에 더하지 않는다.", "",
                  "## 팔 간 비교", "", "차이는 x 팔에서 y 팔을 뺀 값이다.", ""])
    _table(lines, ["셀", "대조", "x", "y", "범위", "HCT 차이(ms)", "95% 구간(ms)",
                   "독립 표본 수", "자유도", "A/A", "자(ms)", "자 표류", "판정"],
           _contrast_rows(statistics, None if result.get("plan_sha256") in MEASURED_PLAN_SHA256 else "해당 없음"))
    if result["task"] in {"X1", "X2", "X6"}:
        secondary = _secondary_contrast_rows(statistics)
        if secondary:
            lines.extend(["같은 대조의 1-RTT 비율과 서버 수신량 차이는 다음과 같다. 비율은 백분율로 환산하지 않았다.", ""])
            _table(lines, ["셀", "대조", "x", "y", "범위", "1-RTT 비율 차이", "95% 구간(비율)",
                           "서버 수신량 차이(B/연결)", "95% 구간(B/연결)"], secondary)
    if result["task"] == "X2" and (uplink_rows := _x2_rows(statistics)):
        lines.extend(["## uplink 오입력 대조", "",
                      "입력별 팔에서 참값 팔을 뺀 HCT 차이다. 궤적 하나 안에서 번인 뒤 블록 평균을 짝지어 "
                      "Student t 구간을 냈고 독립 궤적 반복은 없다. 종류가 A/A인 대조는 입력이 참값과 같은 "
                      "두 팔의 차이라 오입력 효과로 읽지 않는다.", ""])
        _table(lines, ["셀", "대조", "정책 입력(Mbps)", "참값(Mbps)", "종류", "HCT 차이(ms)", "95% 구간(ms)",
                       "짝 블록 수", "자유도", "판정"], uplink_rows)
    if result["task"] == "X1":
        flight = _first_flight_difference_rows(statistics)
        if flight:
            lines.extend(["first flight의 원본과 추가 바이트 차이는 클라이언트 행의 진단이다. "
                          "서버 수신량 비용과 구분하며 값은 x 팔에서 y 팔을 뺀 관측 차이다.", ""])
            _table(lines, ["셀", "대조", "x", "y", "범위", "원본 차이(B)", "추가 차이(B)",
                           "합계 차이(B)", "x 누락 행", "y 누락 행"], flight)
    if result["task"] == "M1":
        drift = statistics.get("a_vs_sealed", result.get("a_vs_sealed", {}))
        if drift:
            lines.extend(["## 봉인 자료와 환경 표류", "", "이 대조는 환경 표류를 보는 탐색 진단이다.", ""])
            _table(lines, ["현재 a HCT(ms)", "봉인 기준 HCT(ms)", "차이(ms)"],
                   [(drift.get("current_mean_ms"), drift.get("sealed_mean_ms"), drift.get("delta_ms"))])
            _table(lines, ["현재 kernel", "봉인 kernel", "봉인 기준 출처"],
                   [(drift.get("kernel"), drift.get("sealed_kernel"), drift.get("source"))])
        lines.extend(["a·e의 동결 서버에는 -conn-log가 없어 최종 stats.conns를 사용했다. "
                      "인증서 DER 크기는 프로세스마다 달라진다. "
                      "사전 설명의 N+5~N+8 B 범위를 넘어선 관측도 아래 표에 그대로 남긴다. "
                      "실제 DER 크기는 저장된 서버 stderr를 근거로 확인하며, "
                      "b·c·d·f의 공통 인증서와 구분한다.", ""])
        certificate_rows = []
        for row in result.get("server_summary", []):
            if row.get("arm") not in {"a", "e"}:
                continue
            value = row.get("certificate_observation", {})
            sizes = value.get("der_bytes_values", [])
            certificate_rows.append((row.get("cell"), row.get("arm"),
                ", ".join(map(_format, sizes)) if sizes else None,
                value.get("units_observed"), value.get("units_total"),
                value.get("source"), value.get("status", "미확인")))
        _table(lines, ["셀", "동결 서버 팔", "관측 DER 크기(B)", "크기 확인 단위", "전체 단위", "원천", "상태"],
               certificate_rows)
    if result["task"] == "X9":
        _pto_tables(lines, statistics)
    if result["task"] == "X6":
        lines.extend(["## 서버 파싱 계수", ""])
        rows = [(row.get("cell"), row.get("arm"), row.get("fec_parse_fail"),
                 row.get("g2auto_ips_used_ge1395"), row.get("client_parity_count_unreliable"))
                for row in result.get("server_summary", [])]
        _table(lines, ["셀", "팔", "서버 fec_parse_fail 합", "g2auto ips_used 1395 이상 행 수",
                       "client_parity_count_unreliable"], rows)
    lines.extend(["## 관측 범위", ""])
    _table(lines, ["셀", "팔", "범위", "유효 RTT 비율", "실제 mean_idle_ms", "idle 상태",
                   "wait_plus_gap 진단(ms)", "C1 경로 제외"], _observation_rows(result.get("observations", {})))
    _table(lines, ["셀", "팔", "one_rtt 분류", "전체 행 수", "수신", "누락", "C1 수신률", "분류 판정", "C1 경로 제외"],
           _feedback_rows(result.get("observations", {})))
    lines.extend(["연결의 절대 시작·완료 시각이 없어 실제 mean_idle_ms는 null·미확인이다. "
                  "feedback 대기와 설정 gap의 합은 wait_plus_gap 진단이며 실제 idle의 대체값이 아니다. "
                  "X6의 실제 idle 차이 기준은 미확인으로 남긴다. C1은 표준 QUIC에 없는 서버 datagram 회신이다.",
                  "", "## 한계", ""])
    if limit := _limits(result):
        lines.append(limit)
    return "\n".join(lines).rstrip() + "\n"


def _cells(line):
    if not line.lstrip().startswith("|"):
        return None
    text = line.strip()[1:]
    if text.endswith("|"):
        text = text[:-1]
    result, value, escaped, ticks = [], [], False, False
    for char in text:
        if escaped:
            value.extend(("\\", char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "`":
            ticks = not ticks
            value.append(char)
        elif char == "|" and not ticks:
            result.append("".join(value).strip())
            value = []
        else:
            value.append(char)
    if escaped:
        value.append("\\")
    result.append("".join(value).strip())
    if ticks:
        raise ValueError("닫히지 않은 표 셀 코드 구간")
    return result


def _decode(value):
    text = value.strip()
    if text.startswith("`") and text.endswith("`"):
        text = text[1:-1]
    text = text.replace("\\|", "|")
    if text.startswith('"'):
        value = json.loads(text)
        if not isinstance(value, str):
            raise ValueError("정오표 문자열 셀이 필요하다")
        return value
    return text.replace("<br>", "\n")


def _section(text, title):
    selected, depth, result = False, None, []
    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            if selected and len(match[1]) <= depth:
                break
            if not selected and match[2] == title:
                selected, depth = True, len(match[1])
                continue
        if selected:
            result.append(line)
    if not selected:
        raise ValueError("지정한 측정 절이 없다: " + title)
    return result


def _lookup(value, key):
    if key.startswith("/"):
        parts = [part.replace("~1", "/").replace("~0", "~") for part in key[1:].split("/")]
    else:
        key = key.removeprefix("$.").removeprefix("$")
        parts = []
        for match in re.finditer(r"([^.\[\]]+)|\[([^\]]+)\]", key):
            token = match[1] if match[1] is not None else match[2]
            if token.startswith('"'):
                token = json.loads(token)
            elif token.startswith("'") and token.endswith("'"):
                token = token[1:-1]
            parts.append(token)
        if not parts:
            raise ValueError("결과 근거 키가 비어 있다")
    for part in parts:
        if isinstance(value, list):
            if not part.isdecimal():
                raise ValueError("결과 배열에는 명시한 인덱스가 필요하다: " + key)
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise ValueError("결과 근거 키를 따라갈 수 없다: " + key)
    return value


def _numeric_leaves(value):
    if _finite(value):
        return [value]
    if isinstance(value, list):
        return [number for item in value for number in _numeric_leaves(item)]
    raise ValueError("근거 키는 수치 또는 수치 배열을 가리켜야 한다")


def _numbers(text):
    text = _IDENTIFIER.sub(" ", text.replace("−", "-"))
    text = re.sub(r"(?:Fig\.|Table|그림|표)\s*\d+", " ", text)
    text = re.sub(r"95\s*%\s*(?:신뢰\s*)?구간", "구간", text)
    values = []
    for match in _NUMBER.finditer(text):
        number = Decimal(match[0].replace(",", ""))
        suffix = text[match.end():].lstrip()
        values.append((number, suffix.startswith("%")))
    return values


def _matches(displayed, source, percent):
    actual = Decimal(str(source)) * (100 if percent else 1)
    quantum = Decimal(1).scaleb(displayed.as_tuple().exponent)
    try:
        return actual.quantize(quantum) == displayed
    except InvalidOperation:
        return False


def _check_errata(path, section, repo_root):
    lines = _section(path.read_text(encoding="utf-8"), section)
    checked, header = 0, None
    for number, line in enumerate(lines, 1):
        cells = _cells(line)
        if cells is None:
            header = None
            continue
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        if "new" in cells and "근거 키" in cells:
            header = cells
            continue
        if header is None:
            continue
        if len(header) != len(cells):
            raise ValueError(f"측정 절 {number}행의 표 칸 수가 다르다")
        row = dict(zip(header, map(_decode, cells)))
        evidence = row["근거 키"]
        if "g3/v33/results/" not in evidence:
            continue
        references = list(_EVIDENCE.finditer(evidence))
        if not references:
            raise ValueError("결과 파일과 명시한 JSON 키가 필요하다: " + evidence)
        sources = []
        for match in references:
            result_path = (repo_root / match[1]).resolve()
            if not result_path.is_relative_to((repo_root / "g3/v33/results").resolve()):
                raise ValueError("결과 근거 경로가 results 밖이다")
            data = json.loads(result_path.read_text(encoding="utf-8"))
            try:
                sources.extend(_numeric_leaves(_lookup(data, match[2])))
            except (KeyError, IndexError) as exc:
                raise ValueError("결과 근거 키가 없다: " + match[2]) from exc
        numbers = _numbers(row.get(_SELECTED_COLUMNS.get(row.get("selected"), "new"), row["new"]))
        if not numbers:
            raise ValueError("대조할 new 숫자가 없다")
        for displayed, percent in numbers:
            indices = [index for index, value in enumerate(sources) if _matches(displayed, value, percent)]
            if not indices:
                raise ValueError(f"new 숫자가 지정한 결과 키와 다르다: {displayed}")
            sources.pop(indices[0])
        if sources:
            raise ValueError("지정한 결과 키의 숫자가 new에 모두 나타나지 않는다")
        checked += 1
    if checked == 0:
        raise ValueError("지정한 절에 대조할 측정 행이 없다")
    return {"status": "pass", "checked_rows": checked, "section": section}


def check_document(path, *, section=None, result=None, repo_root=None):
    path = Path(path)
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    if section is not None:
        return _check_errata(path, section, root)
    text = path.read_text(encoding="utf-8")
    if result is None:
        match = re.search(r"결과 근거: `(g3/v33/results/[A-Za-z0-9_.-]+\.json)`\.", text)
        if match is None:
            raise ValueError("생성 문서의 결과 근거가 없다")
        result = json.loads((root / match[1]).read_text(encoding="utf-8"))
    if text != render_document(result):
        raise ValueError("생성 문서가 결과 JSON에서 만든 문서와 다르다")
    return {"status": "pass", "checked_documents": 1}
