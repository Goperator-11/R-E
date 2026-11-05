from dataclasses import dataclass


MAX_HELLO_BYTES = 65536
MAX_PACKETS = 64


def integer(name, value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in {lower}..{upper}")
    return value


def varint_size(value):
    integer("varint", value, 0, (1 << 62) - 1)
    if value < 64:
        return 1
    if value < 16384:
        return 2
    if value < 1 << 30:
        return 4
    return 8


def effective_initial_size(requested):
    integer("requested Initial size", requested, 0, 65535)
    return 1280 if requested == 0 else min(1452, max(1200, requested))


def packet_number_size(number):
    integer("packet number", number, 0, (1 << 32) - 1)
    outstanding = number + 1
    if outstanding < 1 << 15:
        return 2
    if outstanding < 1 << 23:
        return 3
    return 4


def max_crypto_data(frame_budget, offset):
    integer("frame budget", frame_budget, 0, 1452)
    integer("CRYPTO offset", offset, 0, MAX_HELLO_BYTES)
    header = 2 + varint_size(offset)
    if header > frame_budget:
        return 0
    capacity = frame_budget - header
    if varint_size(capacity) != 1:
        capacity -= 1
    return capacity


@dataclass(frozen=True)
class FirstHello:
    crypto_bytes: int
    dcid_bytes: int
    scid_bytes: int
    token_bytes: int
    complete: bool
    scrambled: bool
    before_response: bool
    first_packet_number: int = 0

    def __post_init__(self):
        integer("ClientHello bytes", self.crypto_bytes, 4, MAX_HELLO_BYTES)
        integer("DCID bytes", self.dcid_bytes, 0, 20)
        integer("SCID bytes", self.scid_bytes, 0, 20)
        integer("token bytes", self.token_bytes, 0, 4096)
        integer("first packet number", self.first_packet_number, 0, (1 << 32) - MAX_PACKETS)
        for name in ("complete", "scrambled", "before_response"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be an explicit boolean")
        if not self.complete or self.scrambled or not self.before_response:
            raise ValueError("requires complete unscrambled ClientHello before response")


@dataclass(frozen=True)
class InitialPacket:
    number: int
    number_bytes: int
    header_bytes: int
    crypto_offset: int
    crypto_bytes: int
    crypto_header_bytes: int
    padding_bytes: int
    datagram_bytes: int


def packetize(hello, width):
    if not isinstance(hello, FirstHello):
        raise ValueError("hello must be FirstHello")
    integer("effective Initial size", width, 1200, 1452)
    offset = 0
    packets = []
    while offset < hello.crypto_bytes:
        if len(packets) >= MAX_PACKETS:
            raise ValueError("ClientHello exceeds reference packet limit")
        number = hello.first_packet_number + len(packets)
        number_bytes = packet_number_size(number)
        header = (9 + hello.dcid_bytes + hello.scid_bytes + number_bytes
                  + varint_size(hello.token_bytes) + hello.token_bytes)
        frame_budget = width - header - 16
        if frame_budget < 0:
            raise ValueError("token and header exceed Initial capacity")
        capacity = max_crypto_data(frame_budget, offset)
        if capacity == 0:
            raise ValueError("Initial has no CRYPTO capacity")
        size = min(capacity, hello.crypto_bytes - offset)
        crypto_header = 1 + varint_size(offset) + varint_size(size)
        padding = width - header - 16 - crypto_header - size
        if padding < 0:
            raise ValueError("negative Initial padding")
        packets.append(InitialPacket(number, number_bytes, header, offset,
                                     size, crypto_header, padding, width))
        offset += size
    return tuple(packets)


def natural_k(hello, width):
    return len(packetize(hello, width))


def width_intervals(hello, lower=1200, upper=1452):
    integer("lower width", lower, 1200, 1452)
    integer("upper width", upper, lower, 1452)
    intervals = []
    for width in range(lower, upper + 1):
        k = natural_k(hello, width)
        if intervals and intervals[-1]["k"] == k:
            intervals[-1]["last_width"] = width
        else:
            intervals.append(dict(first_width=width, last_width=width, k=k))
    return intervals
