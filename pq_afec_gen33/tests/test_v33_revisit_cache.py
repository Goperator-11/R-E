from copy import deepcopy
import json

import pytest

from experiments.v33.revisit_cache import ObservationCache, STATE_VERSION


def record(cache, seq=0, name='origin', **changes):
    values = dict(token_supplied=False, retry_accepted=False, ticket_offered=False,
                  tls_resumed=False, ok=True, hct_ms=10.0, server_bytes=6000, k_obs=2)
    values.update(changes)
    return cache.record(seq, name, **values)


def views(cache, name='origin', **changes):
    values = dict(token_supplied=False, retry_accepted=False, ticket_offered=True)
    values.update(changes)
    return cache.planning_views(name, **values)


def test_ticket_offer_does_not_select_future_tls_result():
    c = ObservationCache()
    record(c, 0, ticket_offered=True, tls_resumed=False, server_bytes=6000)
    record(c, 1, ticket_offered=True, tls_resumed=True, server_bytes=500)
    got = views(c)
    assert [x['key'][2] for x in got] == ['full', 'resumed']
    assert [x['summary']['server_bytes'] for x in got] == [[6000], [500]]
    assert views(c, ticket_offered=False) == got[:1]
    with pytest.raises(TypeError):
        views(c, tls_resumed=True)


def test_unknown_tls_and_missing_metrics_stay_unknown():
    c = ObservationCache()
    record(c, tls_resumed=None, hct_ms=None, server_bytes=None, k_obs=None)
    assert all(x['summary']['observations'] == 0 for x in views(c))
    group = c.to_dict()['destinations'][0]['groups'][0]
    assert group['tls'] == 'unknown'
    assert group['observations'][0]['hct_ms'] is None


def test_failed_connections_are_not_zero_success_samples():
    c = ObservationCache()
    record(c, ok=False, hct_ms=300.0, server_bytes=123, k_obs=2)
    summary = views(c)[0]['summary']
    assert summary == dict(observations=1, successes=0, failures=1, token_rejections=0,
                           hct_ms=[], server_bytes=[], k_obs=[])


@pytest.mark.parametrize('retry', [False, True])
def test_invalid_token_plans_new_attempt_without_token(retry):
    c = ObservationCache()
    result = record(c, token_supplied=not retry, retry_accepted=retry,
                    token_rejected=True, tls_resumed=None, ok=False,
                    hct_ms=None, server_bytes=None, k_obs=None)
    assert result['restart_without_token'] and result['reuse_connection'] is False
    assert result['key'][1] == ('retry_unknown' if retry else 'token_unknown')
    record(c, 1, token_supplied=False, ticket_offered=True, tls_resumed=True)
    assert views(c)[1]['summary']['successes'] == 1
    assert views(c, token_supplied=True)[1]['summary']['observations'] == 0


@pytest.mark.parametrize('changes', [
    {'token_supplied': 1}, {'retry_accepted': 0}, {'ticket_offered': 1},
    {'tls_resumed': 'yes'}, {'ok': 1}, {'token_rejected': 0},
    {'hct_ms': float('nan')}, {'hct_ms': float('inf')}, {'hct_ms': True}, {'hct_ms': 0},
    {'hct_ms': -1}, {'server_bytes': -1}, {'server_bytes': True}, {'server_bytes': 1.5},
    {'k_obs': 0}, {'k_obs': 33}, {'k_obs': False}, {'k_obs': 2.5},
    {'tls_resumed': True}, {'token_rejected': True},
    {'token_rejected': True, 'ok': False},
    {'token_rejected': True, 'token_supplied': True},
])
def test_invalid_observation_is_atomic(changes):
    c = ObservationCache()
    record(c)
    before = c.to_dict()
    with pytest.raises(ValueError):
        record(c, 1, **changes)
    assert c.to_dict() == before


@pytest.mark.parametrize('seq', [-1, 0, True, 1.1, 1 << 63])
def test_sequence_rejects_duplicate_and_invalid_inputs(seq):
    c = ObservationCache()
    record(c)
    before = c.to_dict()
    with pytest.raises(ValueError):
        record(c, seq)
    assert c.to_dict() == before


@pytest.mark.parametrize('name', ['', None, True, 'x' * 4097])
def test_destination_input_rejected_atomically(name):
    c = ObservationCache()
    before = c.to_dict()
    with pytest.raises(ValueError):
        record(c, name=name)
    assert c.to_dict() == before


def test_all_client_address_tls_groups_roundtrip_and_copies():
    c = ObservationCache()
    seq = 0
    for name in ('alpha', 'beta'):
        for token, retry in ((False, False), (True, False), (False, True)):
            for tls in (False, True, None):
                record(c, seq, name, token_supplied=token, retry_accepted=retry,
                       ticket_offered=True, tls_resumed=tls)
                seq += 1
    value = c.to_dict()
    restored = ObservationCache.from_dict(json.loads(json.dumps(value, allow_nan=False)))
    assert restored.to_dict() == value and len(value['destinations'][0]['groups']) == 9
    value['destinations'][0]['groups'][0]['observations'][0]['server_bytes'] = 0
    assert c.to_dict() == restored.to_dict()
    lookup = views(c, 'alpha')
    lookup[0]['observations'][0]['server_bytes'] = -1
    assert c.to_dict() == restored.to_dict()


def test_window_lru_and_read_does_not_refresh_destination():
    c = ObservationCache(max_destinations=2, window=2)
    record(c, 0, 'a')
    record(c, 1, 'a')
    record(c, 2, 'a')
    assert [x['sequence'] for x in views(c, 'a')[0]['observations']] == [1, 2]
    record(c, 3, 'b')
    views(c, 'a')
    record(c, 4, 'c')
    assert [x['name'] for x in c.to_dict()['destinations']] == ['b', 'c']
    assert views(c, 'a')[0]['summary']['observations'] == 0
    record(c, 5, 'b')
    assert [x['name'] for x in c.to_dict()['destinations']] == ['c', 'b']
    assert ObservationCache.from_dict(c.to_dict()).to_dict() == c.to_dict()


@pytest.mark.parametrize('name,value', [('max_destinations', 0), ('max_destinations', True),
                                       ('max_destinations', 1025), ('window', 0),
                                       ('window', False), ('window', 1025)])
def test_invalid_limits(name, value):
    with pytest.raises(ValueError):
        ObservationCache(**{name: value})


@pytest.mark.parametrize('version', [0, 4, True, '1', None])
def test_rejects_legacy_or_unknown_version(version):
    value = ObservationCache().to_dict()
    value['version'] = version
    with pytest.raises(ValueError):
        ObservationCache.from_dict(value)
    with pytest.raises(ValueError):
        ObservationCache.from_dict({'v': 4, 'k_hist': []})


def populated():
    c = ObservationCache(max_destinations=2, window=2)
    record(c, 0, 'a')
    record(c, 1, 'b')
    return c.to_dict()


@pytest.mark.parametrize('mutate', [
    lambda v: v.update(extra=True),
    lambda v: v.update(last_sequence=True),
    lambda v: v.update(last_sequence=5),
    lambda v: v.update(destinations={}),
    lambda v: v['destinations'].append(deepcopy(v['destinations'][0])),
    lambda v: v['destinations'].reverse(),
    lambda v: v['destinations'][0]['groups'].append(deepcopy(v['destinations'][0]['groups'][0])),
    lambda v: v['destinations'][0]['groups'][0].update(address='token_validated'),
    lambda v: v['destinations'][0]['groups'][0].update(tls='future'),
    lambda v: v['destinations'][0]['groups'][0].update(observations=[]),
    lambda v: v['destinations'][0]['groups'][0]['observations'][0].update(extra=True),
    lambda v: v['destinations'][0]['groups'][0]['observations'][0].update(hct_ms=float('nan')),
    lambda v: v['destinations'][0]['groups'][0]['observations'][0].update(token_supplied=True),
    lambda v: v['destinations'][1]['groups'][0]['observations'][0].update(sequence=0),
    lambda v: v['destinations'][0]['groups'][0]['observations'].append(deepcopy(v['destinations'][0]['groups'][0]['observations'][0])),
])
def test_malformed_state_is_rejected_without_input_mutation(mutate):
    value = populated()
    mutate(value)
    encoded = json.dumps(value, sort_keys=True)
    with pytest.raises(ValueError):
        ObservationCache.from_dict(value)
    assert json.dumps(value, sort_keys=True) == encoded


def test_new_empty_format_and_invalid_missing_values():
    c = ObservationCache()
    assert c.to_dict()['version'] == STATE_VERSION == 1
    assert ObservationCache.from_dict(c.to_dict()).to_dict() == c.to_dict()
    with pytest.raises(ValueError):
        views(c, token_supplied=None)
    with pytest.raises(ValueError):
        views(c, ticket_offered=None)
