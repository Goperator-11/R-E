from dataclasses import replace

import pytest

from experiments.v33.natural_k_reference import (
    FirstHello, effective_initial_size, max_crypto_data, natural_k,
    packet_number_size, packetize, varint_size, width_intervals,
)


HELLO = FirstHello(1447, 10, 4, 0, True, False, True)


@pytest.mark.parametrize("value,size", [(0, 1), (63, 1), (64, 2), (16383, 2),
    (16384, 4), ((1 << 30) - 1, 4), (1 << 30, 8), ((1 << 62) - 1, 8)])
def test_varint_boundaries(value, size):
    assert varint_size(value) == size


@pytest.mark.parametrize("value", [True, False, -1, 1.0, None, 1 << 62])
def test_varint_rejects_invalid(value):
    with pytest.raises(ValueError):
        varint_size(value)


@pytest.mark.parametrize("value,expected", [(0, 1280), (1, 1200), (1199, 1200),
    (1200, 1200), (1280, 1280), (1452, 1452), (1472, 1452), (65535, 1452)])
def test_effective_width(value, expected):
    assert effective_initial_size(value) == expected


@pytest.mark.parametrize("value", [-1, 65536, True, 1280.0])
def test_invalid_requested_width(value):
    with pytest.raises(ValueError):
        effective_initial_size(value)


@pytest.mark.parametrize("number,size", [(0, 2), (32766, 2), (32767, 3),
    (8388606, 3), (8388607, 4), ((1 << 32) - 1, 4)])
def test_packet_number_boundaries(number, size):
    assert packet_number_size(number) == size


def test_max_data_matches_exhaustive_frame_lengths():
    for offset in (0, 63, 64, 16383, 16384, 65536):
        for budget in range(1453):
            capacity = max_crypto_data(budget, offset)
            fits = lambda n: 1 + varint_size(offset) + varint_size(n) + n <= budget
            assert capacity == 0 or fits(capacity)
            assert not fits(capacity + 1)


def test_known_packet_ranges():
    packets = packetize(HELLO, 1280)
    assert [(p.crypto_offset, p.crypto_bytes) for p in packets] == [(0, 1234), (1234, 213)]
    assert [(p.header_bytes, p.crypto_header_bytes, p.padding_bytes) for p in packets] == [(26, 4, 0), (26, 5, 1020)]


@pytest.mark.parametrize("field,value", [("complete", False), ("scrambled", True),
    ("before_response", False), ("complete", 1), ("scrambled", 0),
    ("before_response", None), ("crypto_bytes", 3), ("crypto_bytes", 65537),
    ("dcid_bytes", 21), ("scid_bytes", -1), ("token_bytes", 4097),
    ("crypto_bytes", True), ("first_packet_number", -1)])
def test_unsupported_inputs_fail_explicitly(field, value):
    with pytest.raises(ValueError):
        replace(HELLO, **{field: value})


@pytest.mark.parametrize("width", [0, 1199, 1453, True, 1280.0])
def test_effective_width_must_already_be_normalized(width):
    with pytest.raises(ValueError):
        packetize(HELLO, width)


def test_tokens_reduce_capacity_with_varint_boundary():
    sizes = [packetize(replace(HELLO, token_bytes=n), 1280)[0].crypto_bytes for n in (0, 63, 64)]
    assert sizes == [1234, 1171, 1169]


def test_no_capacity_does_not_loop():
    with pytest.raises(ValueError, match="capacity"):
        packetize(replace(HELLO, token_bytes=1300), 1200)


def test_packet_limit_is_not_policy_k_limit():
    assert natural_k(replace(HELLO, crypto_bytes=9600), 1280) == 8
    with pytest.raises(ValueError, match="packet limit"):
        packetize(replace(HELLO, crypto_bytes=65536, token_bytes=1000), 1200)


def test_packet_number_transition_changes_header_capacity():
    got = packetize(replace(HELLO, first_packet_number=32766), 1280)
    assert [p.number_bytes for p in got] == [2, 3]
    assert [p.header_bytes for p in got] == [26, 27]


def test_offset_transition_and_exact_fit():
    for offset in (63, 64, 16383, 16384):
        assert max_crypto_data(1200, offset) == 1197 - varint_size(offset)
    for size, k in ((1234, 1), (1235, 2), (2467, 2), (2468, 3)):
        assert natural_k(replace(HELLO, crypto_bytes=size), 1280) == k


def test_width_intervals_show_repacking_boundary():
    h = replace(HELLO, crypto_bytes=1250)
    assert width_intervals(h) == [dict(first_width=1200, last_width=1295, k=2),
                                  dict(first_width=1296, last_width=1452, k=1)]
    assert natural_k(h, 1280) != natural_k(h, 1300)


def test_no_mutation_and_byte_conservation():
    for length in (4, 63, 64, 1148, 1250, 1447, 9600, 16384, 65536):
        h = replace(HELLO, crypto_bytes=length)
        for width in (1200, 1280, 1452):
            got = packetize(h, width)
            assert sum(p.crypto_bytes for p in got) == length
            assert all(p.header_bytes + 16 + p.crypto_header_bytes + p.crypto_bytes + p.padding_bytes == width for p in got)
            assert got == packetize(h, width)
            assert all(a.crypto_offset + a.crypto_bytes == b.crypto_offset for a, b in zip(got, got[1:]))
