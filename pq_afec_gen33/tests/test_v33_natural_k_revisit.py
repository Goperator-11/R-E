import copy
import json
from pathlib import Path

from cryptography.exceptions import InvalidTag
import pytest

from experiments.v33.natural_k_revisit import first_hello


def fixture(name="token_resume"):
    path = Path(__file__).parent / "fixtures/o4_first_hello_v1" / (name + ".json")
    return json.loads(path.read_text(encoding="utf-8"))


def check(data):
    return first_hello(data["events"], data["observation"], data["width"])


def test_real_token_and_resumed_hello():
    got = check(fixture())
    assert got["natural_k"] == 2 and got["input"]["token_bytes"] > 0
    assert got["input"]["crypto_bytes"] > 1600


def test_post_hello_probe_does_not_increase_natural_k():
    got = check(fixture("pto_after_hello"))
    assert got["natural_k"] == 2
    assert got["later_initial_before_response"] == 2


@pytest.mark.parametrize("mode", ["missing", "duplicate", "reverse", "crc", "ack", "early_response", "truncated", "width"])
def test_incomplete_or_unowned_first_flight_rejected(mode):
    data = fixture()
    if mode == "missing":
        data["events"] = data["events"][:1]
    elif mode == "duplicate":
        data["events"].insert(1, copy.deepcopy(data["events"][0]))
    elif mode == "reverse":
        data["events"][0], data["events"][1] = data["events"][1], data["events"][0]
    elif mode == "crc":
        data["events"][0]["crc32c"] ^= 1
    elif mode == "ack":
        p = next(p for p in data["observation"]["packets"] if p["direction"] == "sent" and p["space"] == "initial")
        p["ack_ranges"] = [[0, 0]]
    elif mode == "early_response":
        p = next(p for p in data["observation"]["packets"] if p["direction"] == "received")
        p["at_ns"] = 0
    elif mode == "truncated":
        data["observation"]["truncated"] = True
    elif mode == "width":
        data["width"] += 1
    with pytest.raises(AssertionError):
        check(data)


@pytest.mark.parametrize("mode", ["tag", "dcid"])
def test_authenticated_wire_required(mode):
    data = fixture()
    packet = bytearray.fromhex(data["events"][0]["wire_hex"])
    packet[-1 if mode == "tag" else 6] ^= 1
    data["events"][0]["wire_hex"] = packet.hex()
    with pytest.raises(InvalidTag):
        check(data)
