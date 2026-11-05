import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value, digits=6):
    return "미확정" if value is None else f"{value:.{digits}f}"


def action(value):
    return "(" + ",".join(map(str, value)) + ")"


def render(model, world):
    lines = ["# M1 고정 행동의 비용과 첫 비행 실패", "",
        "큰 인증서16000 B, 원본2개, W1280 B, RTT50 ms, 업링크2 Mbps의 개발 계산이다. 행동은 (δ,lead,T)이며 미리 고정한16개만 비교한다. 차이는 hold에서 off를 뺀 값으로 음수이면 감소다. 모든 비용과 구간의 단위는ms/연결이다.", "",
        "model-world J는 첫 비행과 실패 가지의 비용식이다. 독립 사건 세계 HCT는 재전송을 포함한 MC 기대값이다. 두 값을 같은 결과로 합치지 않는다. 세계 구간은277행동 가족의 공동99% 오차를 반영한 정규근사이며, 영분산의 구조적 증명이 없으면 미확정이다.", "",
        "## 고정 집합의 최솟값", "",
        "| p | 자료 | off 행동 | off 비용 (ms) | hold 행동 | hold 비용 (ms) | 차이 (ms) | 차이 구간 (ms) |",
        "|---|---|---|---:|---|---:|---:|---|"]
    for probability in (.02, .15):
        row = next(r for r in model["best"] if r["p"] == probability)
        lines.append(f'| {probability} | model-world J | {action(row["off_action"])} | {number(row["off_J_ms"])} | {action(row["hold_action"])} | {number(row["hold_J_ms"])} | {number(-row["improvement_ms"])} | 결정적 열거 |')
        row = next(r for r in world["finite_design_minima"] if r["p"] == probability)
        interval = "미확정" if row["lower_ms"] is None else f'[{number(row["lower_ms"])}, {number(row["upper_ms"])}]'
        lines.append(f'| {probability} | 사건 세계 MC | {action(row["off"]["action"])} | {number(row["off"]["mean_hct_ms"])} | {action(row["hold"]["action"])} | {number(row["hold"]["mean_hct_ms"])} | {number(row["hold_minus_off_ms"])} | {interval} |')
    lines += ["", "행동은 점추정의 최선이다. 최솟값 구간은16개 행동 모두의 구간 끝점에서 구하므로 점추정 최선 행동의 구간과 다를 수 있다. 전역 최적 행동이나 정책의 후회를 뜻하지 않는다.", "",
        "## 행동별 차이와 보류 기한", "",
        "명목 기한은 모형의 첫 패리티 이후 남은 슬롯 직렬화와 margin이다. 표의 세계 상한 비교는 고정 계획의 진단이며 전체 정책의0.5 ms 비열등 관문을 대체하지 않는다."]
    for probability in (.02, .15):
        lines += ["", f"### p={probability}", "",
            "| 행동 | model J 차이 (ms) | 명목 기한 (ms) | 세계 HCT 차이 (ms) | 세계 차이 구간 (ms) | 세계 상한≤명목 기한 |",
            "|---|---:|---:|---:|---|---|"]
        for row in world["fixed_differences"]:
            if row["p"] != probability:
                continue
            interval = "미확정" if row["lower_ms"] is None else f'[{number(row["lower_ms"])}, {number(row["upper_ms"])}]'
            within = {True: "예", False: "아니오", None: "미확정"}[row["independent_world_upper_within_nominal_bound"]]
            lines.append(f'| {action(row["action"])} | {number(row["model_hold_minus_off_ms"])} | {number(row["model_nominal_deadline_bound_ms"])} | {number(row["hold_minus_off_ms"])} | {interval} | {within} |')
    lines += ["", "## 첫 비행 소거 집합의 전수 확률", "",
        "재전송을 끄고 후속 도착을 고정한 첫 비행 검사다. 전체 연결의 실패 확률이나 HCT 기대값으로 해석하지 않는다.", "",
        "| p | 행동 | 열거 패턴 | 실패 패턴 | 독립 세계 첫 비행 실패 확률 | 모형 실패 확률 |",
        "|---|---|---:|---:|---:|---:|"]
    for row in model["exact_first_flight"]:
        lines.append(f'| {row["p"]} | {action(row["action"])} | {row["patterns"]} | {row["failed"]} | {row["independent_first_flight_p_fail"]:.15g} | {row["model_p_fail"]:.15g} |')
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    for name in ("model", "world", "check", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    model, world, check = map(read, (args.model, args.world, args.check))
    assert check["status"] == "pass" and check["report_sha256"] == sha(args.world)
    assert world["model_source_sha256"] == sha(args.model)
    assert len(world["fixed_rows"]) == 64 and len(world["fixed_differences"]) == 32
    text = render(model, world)
    text += "\n출처 파일 지문:\n\n"
    for path in (args.model, args.world, args.check):
        text += f"- `{path.name}`: `{sha(path)}`\n"
    text += f"- 생성기 `{Path(__file__).name}`: `{sha(__file__)}`\n"
    with args.out.open("x", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(json.dumps(dict(output=str(args.out), sha256=sha(args.out), fixed_rows=64, fixed_differences=32)))


if __name__ == "__main__":
    main()
