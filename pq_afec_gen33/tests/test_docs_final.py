from pathlib import Path
import re

from padfec import policy
from padfec3 import decide3, layout, learn3


def test_spec_v331_constants_match_current_policy():
    text = (Path(__file__).resolve().parents[1] / "docs" / "PAD-FEC v3.3.1 명세.md").read_text(encoding="utf-8")
    scope = text.split("## 0. 범위\n", 1)[1].split("\n## 1.", 1)[0]
    rows = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \|", scope, re.MULTILINE)
    assert len(rows) == len({name for name, _ in rows}), "duplicate specification constants"
    values = dict(rows)
    assert values["POLICY_VERSION"] == learn3.POLICY_VERSION
    assert int(values["STATE_VERSION"]) == learn3.STATE_VERSION
    assert int(values["UDP_MAX"]) == decide3.UDP_MAX == policy.QUICGO_MAX_IPS
    assert float(values["EPS"]) == learn3.EPS
    assert float(values["CLASS_EPS"]) == learn3.CLASS_EPS
    actions = text.split("## 2. 행동과 first flight 배치\n", 1)[1].split("\n## 3.", 1)[0]
    bounds = actions.split("| k | parity 후보의 W_eff 상한 (B) |\n", 1)[1].split("\n\n", 1)[0]
    limits = re.findall(r"^\| (\d+) \| (\d+) \|$", bounds, re.MULTILINE)
    assert len(limits) == layout.K_MAX
    assert [int(k) for k, _ in limits] == list(range(1, layout.K_MAX + 1))
    for k_text, limit_text in limits:
        k, limit = int(k_text), int(limit_text)
        assert limit == decide3.UDP_MAX - layout.parity_bytes(0, k)
        assert layout.parity_bytes(limit, k) == decide3.UDP_MAX
        assert layout.parity_bytes(limit + 1, k) > decide3.UDP_MAX
