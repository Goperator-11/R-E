import pytest
import json
from pathlib import Path

from experiments.v33.revisit_capture import client_hello_extensions, first_client_hello


def hello(extensions):
    body = bytes.fromhex('0303') + bytes(32) + b'\0\0\2\x13\x01\1\0' + len(extensions).to_bytes(2, 'big') + extensions
    return b'\1' + len(body).to_bytes(3, 'big') + body


def test_extensions_preserve_offer_without_assuming_acceptance():
    value = hello(b'\0\x29\0\2ab\0\x2d\0\2\1\1')
    assert client_hello_extensions(value) == {41: b'ab', 45: b'\1\1'}
    assert client_hello_extensions(hello(b'\0\x2d\0\2\1\1')) == {45: b'\1\1'}


@pytest.mark.parametrize('value', [b'', b'\1\0\0\0', hello(b'')[:-1], hello(b'') + b'\0',
                                   hello(b'\0\x29\0'), hello(b'\0\x29\0\2a'),
                                   hello(b'\0\x29\0\0\0\x29\0\0')])
def test_malformed_hello_rejected(value):
    with pytest.raises(ValueError):
        client_hello_extensions(value)


def test_empty_capture_is_not_no_ticket_observation():
    with pytest.raises(ValueError, match='incomplete'):
        first_client_hello([])


def test_dropped_first_original_is_missing_ticket_input():
    path = Path(__file__).resolve().parents[1] / 'g3/v33/fixtures/M4_missing_initial.json'
    events = json.loads(path.read_text(encoding='utf-8'))['events']
    with pytest.raises(ValueError, match='incomplete before DCID transition'):
        first_client_hello(events)
