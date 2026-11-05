import hashlib

from experiments.v33 import initial_inspect as wire


def client_hello_extensions(hello):
    if not isinstance(hello, bytes) or len(hello) < 40 or hello[0] != 1 or len(hello) != 4 + int.from_bytes(hello[1:4], 'big'):
        raise ValueError('invalid ClientHello length')
    pos = 38
    def vector(width):
        nonlocal pos
        if pos + width > len(hello):
            raise ValueError('truncated vector length')
        n = int.from_bytes(hello[pos:pos + width], 'big')
        pos += width
        if pos + n > len(hello):
            raise ValueError('truncated vector')
        value = hello[pos:pos + n]
        pos += n
        return value
    vector(1)
    vector(2)
    vector(1)
    extensions = vector(2)
    if pos != len(hello):
        raise ValueError('trailing ClientHello bytes')
    result = {}
    pos = 0
    while pos < len(extensions):
        if pos + 4 > len(extensions):
            raise ValueError('truncated extension header')
        kind = int.from_bytes(extensions[pos:pos + 2], 'big')
        n = int.from_bytes(extensions[pos + 2:pos + 4], 'big')
        pos += 4
        if pos + n > len(extensions) or kind in result:
            raise ValueError('truncated or duplicate extension')
        result[kind] = extensions[pos:pos + n]
        pos += n
    return result


def first_client_hello(events):
    pieces = {}
    key = dcid_first = None
    token = scid = None
    packets = 0
    for event in events:
        if not event['initial'] or event['parity'] or not event.get('wire_hex'):
            continue
        data = bytes.fromhex(event['wire_hex'])
        for typ, start, pos, end, dcid in wire.packets(data):
            if typ != 0 or data[pos:pos + 4] == b'JUNK':
                continue
            if dcid_first is not None and dcid != dcid_first:
                raise ValueError('first ClientHello incomplete before DCID transition')
            if key is None:
                key, dcid_first = wire.keys(dcid), dcid
                at = start + 6 + data[start + 5]
                n = data[at]
                scid = data[at + 1:at + 1 + n].hex()
                token, _ = wire.varint(data, at + 1 + n)
            _, plain = wire.decrypt(data, start, pos, end, key)
            packets += 1
            for offset, body in wire.crypto_frames(plain):
                for i, byte in enumerate(body, offset):
                    if i in pieces and pieces[i] != byte:
                        raise ValueError('conflicting CRYPTO bytes')
                    pieces[i] = byte
            if all(i in pieces for i in range(4)):
                length = 4 + int.from_bytes(bytes(pieces[i] for i in range(1, 4)), 'big')
                if all(i in pieces for i in range(length)):
                    hello = bytes(pieces[i] for i in range(length))
                    ext = client_hello_extensions(hello)
                    return dict(token_bytes=token, scid=scid, client_hello_bytes=length,
                                client_hello_sha256=hashlib.sha256(hello).hexdigest(),
                                authenticated_packets=packets, ticket_offered=41 in ext,
                                extension_ids=list(ext))
    raise ValueError('first ClientHello incomplete')
