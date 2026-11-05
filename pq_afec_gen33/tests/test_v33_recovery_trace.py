import copy
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from experiments.v33.recovery_trace import analyze,intervals,length,overlap,client_wire


def packet(at,pn,crypto=(),direction="sent",space="initial",acks=()):
    return dict(at_ns=at,pn=pn,crypto=list(crypto),direction=direction,space=space,ack_ranges=list(acks),
        bytes=1280,crc32c=100+pn,coalesced=False)


def observation(packets,ptos=()):
    return dict(truncated=False,packets=packets,pto_at_ns=list(ptos))


@pytest.mark.parametrize("ranges,expected",[([],[]),([[0,4],[4,6]],[(0,10)]),([[8,4],[0,3]],[(0,3),(8,12)]),
    ([[0,10],[2,3],[7,8]],[(0,15)]),([[2,8],[0,4]],[(0,10)])])
def test_interval_union_handles_nested_and_adjacent_ranges(ranges,expected):
    assert intervals(ranges)==expected
    assert length(intervals(ranges))==len(set(i for a,n in ranges for i in range(a,a+n)))


def test_partial_overlap_matches_integer_byte_sets():
    for start in range(8):
        a=intervals([[0,4],[6,2]])
        b=intervals([[start,4]])
        assert overlap(a,b)==len({0,1,2,3,6,7}&set(range(start,start+4)))


def test_retransmission_new_bytes_and_acknowledged_overlap_are_separate():
    packets=[packet(1,0,[[0,10]]),packet(2,1,[[10,10]]),packet(5,0,direction="received",acks=[[0,0]]),packet(8,2,[[5,20]])]
    out=analyze(observation(packets,[7]),2,[])
    last=out["crypto_packets"][-1]
    assert (last["repeated_bytes"],last["new_bytes"],last["acked_overlap_bytes"])==(15,5,5)
    assert last["latest_preceding_pto_ns"]==7
    assert not last["before_any_received"] and not last["before_any_initial_ack"]
    assert out["unique_crypto_bytes"]==25
    assert out["server_ack_authenticated"] is False and out["pto_causality"]=="precedence_only"


def test_same_length_distinct_ranges_are_not_retransmissions():
    out=analyze(observation([packet(1,0,[[0,10]]),packet(2,1,[[10,10]])]),1,[])
    assert out["repeated_crypto_packets"]==0 and out["unique_crypto_bytes"]==20


def test_handshake_ack_cannot_ack_initial_crypto():
    out=analyze(observation([packet(1,0,[[0,10]]),packet(2,0,direction="received",space="handshake",acks=[[0,0]]),packet(3,1,[[0,10]])]),1,[])
    assert out["acked_overlap_bytes"]==0 and out["qlog_initial_ack_packets"]==0


def test_acked_retransmission_packet_confirms_original_byte_range():
    out=analyze(observation([packet(1,0,[[0,10]]),packet(2,1,[[0,10]]),packet(3,0,direction="received",acks=[[1,1]]),packet(4,2,[[0,10]])]),1,[])
    assert out["crypto_packets"][-1]["acked_overlap_bytes"]==10


@pytest.mark.parametrize("owner",[[],[packet(3,0,[[0,10]])]])
def test_unseen_or_future_ack_owner_is_rejected(owner):
    with pytest.raises(ValueError,match="unseen or future"):
        analyze(observation([packet(2,0,direction="received",acks=[[0,0]])]+owner),0,[])


def test_duplicate_sent_pn_in_same_space_is_rejected():
    with pytest.raises(ValueError,match="duplicate"):
        analyze(observation([packet(1,0,[[0,10]]),packet(2,0,[[10,10]])]),2,[])


def test_equal_pn_in_different_spaces_is_valid():
    out=analyze(observation([packet(1,0,[[0,10]]),packet(2,0,[[0,10]],space="handshake")]),1,[])
    assert out["unique_crypto_bytes"]==10


@pytest.mark.parametrize("ranges",[[[0,0]],[[-1,2]],[[True,2]],[[1,2,3]]])
def test_invalid_ranges_are_rejected(ranges):
    with pytest.raises(ValueError):intervals(ranges)


def test_nonmonotone_times_and_truncated_observation_are_rejected():
    with pytest.raises(ValueError,match="ordered"):
        analyze(observation([packet(2,0,[[0,1]]),packet(1,1,[[1,1]])]),2,[])
    obs=observation([])
    obs["truncated"]=True
    with pytest.raises(ValueError,match="truncated"):analyze(obs,0,[])


def test_relay_mismatch_is_reported_without_inventing_loss():
    out=analyze(observation([packet(1,0,[[0,10]])]),1,[])
    assert out["relay_unmatched_crypto_packets"]==1
    assert out["authenticated_initial_packets"]==0 and not out["raw_wire_available"]


def test_conflicting_raw_values_under_one_crc_are_rejected():
    events=[dict(direction="c2s",crc32c=100,bytes=1280,dropped=False,wire_hex=x,initial=False) for x in ("00","01")]
    with pytest.raises(ValueError,match="conflicting"):
        analyze(observation([packet(1,0,[[0,10]])]),1,events)


def test_actual_authenticated_initial_rejects_tampering_and_qlog_changes():
    fixture = Path(__file__).resolve().parents[1] / "g3/v33/fixtures/S5_test_inputs_v1/authenticated_initial.json"
    value = json.loads(fixture.read_text(encoding="utf-8"))
    row, events = value["row"], value["events"]
    obs = row["observation"]
    got=analyze(obs,row["first_flight_datagrams"],events)
    assert got["authenticated_crypto_packets"]==2
    bad=copy.deepcopy(events)
    event=next(e for e in bad if e["direction"]=="c2s" and e["initial"] and not e["parity"])
    raw=bytearray.fromhex(event["wire_hex"])
    raw[-1]^=1
    event["wire_hex"]=raw.hex()
    with pytest.raises(InvalidTag):client_wire(bad)
    badobs=copy.deepcopy(obs)
    next(p for p in badobs["packets"] if p["direction"]=="sent" and p["crypto"])["crypto"][0][1]-=1
    with pytest.raises(ValueError,match="authenticated CRYPTO"):analyze(badobs,2,events)


def test_actual_coalesced_datagram_preserves_packet_and_udp_lengths():
    fixture = Path(__file__).resolve().parents[1] / "g3/v33/fixtures/S5_test_inputs_v1/coalesced_initial.json"
    value = json.loads(fixture.read_text(encoding="utf-8"))
    row, events = value["row"], value["events"]
    assert not row["revisit"]["retry_received"]
    raw=client_wire(events)
    item=next(x for x in raw if x["packet_bytes"]!=x["datagram_bytes"])
    assert item["packet_bytes"]==1099 and item["datagram_bytes"]==1280
    got=analyze(row["observation"],row["first_flight_datagrams"],events)
    assert got["authenticated_initial_packets"]==len(raw)
