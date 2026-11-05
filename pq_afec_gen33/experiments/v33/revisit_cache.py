from copy import deepcopy
import math

from experiments.v33.revisit_reference import boolean, integer, observation_key


STATE_VERSION = 1
MAX_SEQUENCE = (1 << 63) - 1
ADDRESSES = ('no_token_unknown', 'token_unknown', 'retry_unknown')
TLS_KINDS = ('full', 'resumed', 'unknown')
OBS_FIELDS = {'sequence', 'ok', 'hct_ms', 'server_bytes', 'k_obs', 'token_rejected', 'token_supplied', 'ticket_offered'}


def destination(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError('destination must be a nonempty string of at most4096 characters')
    return value


def validate_observation(value, address, tls):
    if not isinstance(value, dict) or set(value) != OBS_FIELDS:
        raise ValueError('invalid observation fields')
    integer('sequence', value['sequence'], 0, MAX_SEQUENCE)
    for name in ('ok', 'token_rejected', 'token_supplied', 'ticket_offered'):
        boolean(name, value[name])
    if address not in ADDRESSES or tls not in TLS_KINDS:
        raise ValueError('invalid observation group')
    if address != 'retry_unknown' and (address == 'token_unknown') != value['token_supplied']:
        raise ValueError('token and address group disagree')
    if tls == 'resumed' and not value['ticket_offered']:
        raise ValueError('resumption without ticket offer')
    if value['token_rejected'] and (value['ok'] or not (value['token_supplied'] or address == 'retry_unknown')):
        raise ValueError('token rejection needs a failed token attempt')
    hct = value['hct_ms']
    if hct is not None and (type(hct) not in (int, float) or not math.isfinite(hct) or hct <= 0):
        raise ValueError('observed HCT must be positive finite ms')
    if value['server_bytes'] is not None:
        integer('server_bytes', value['server_bytes'], 0, MAX_SEQUENCE)
    if value['k_obs'] is not None:
        integer('k_obs', value['k_obs'], 1, 32)


def summarize(observations):
    successful = [x for x in observations if x['ok']]
    return dict(observations=len(observations), successes=len(successful),
                failures=len(observations) - len(successful),
                token_rejections=sum(x['token_rejected'] for x in observations),
                hct_ms=[x['hct_ms'] for x in successful if x['hct_ms'] is not None],
                server_bytes=[x['server_bytes'] for x in successful if x['server_bytes'] is not None],
                k_obs=[x['k_obs'] for x in successful if x['k_obs'] is not None])


class ObservationCache:
    def __init__(self, *, max_destinations=16, window=32):
        self.max_destinations = integer('max_destinations', max_destinations, 1, 1024)
        self.window = integer('window', window, 1, 1024)
        self.last_sequence = -1
        self._destinations = []
        self._groups = {}

    def planning_views(self, name, *, token_supplied, retry_accepted, ticket_offered):
        destination(name)
        boolean('ticket_offered', ticket_offered)
        key = observation_key(name, token_supplied=token_supplied, retry_accepted=retry_accepted,
                              server_initially_validated=None, tls_resumed=None)
        kinds = ('full', 'resumed') if ticket_offered else ('full',)
        result = []
        for tls in kinds:
            lookup = key[:2] + (tls,)
            rows = deepcopy(self._groups.get(lookup, []))
            result.append(dict(key=list(lookup), observations=rows, summary=summarize(rows)))
        return result

    def record(self, sequence, name, *, token_supplied, retry_accepted, ticket_offered,
               tls_resumed, ok, hct_ms, server_bytes, k_obs, token_rejected=False):
        destination(name)
        integer('sequence', sequence, 0, MAX_SEQUENCE)
        if sequence <= self.last_sequence:
            raise ValueError('sequence must increase')
        key = observation_key(name, token_supplied=token_supplied, retry_accepted=retry_accepted,
                              server_initially_validated=None, tls_resumed=tls_resumed)
        value = dict(sequence=sequence, ok=ok, hct_ms=hct_ms, server_bytes=server_bytes,
                     k_obs=k_obs, token_rejected=token_rejected, token_supplied=token_supplied,
                     ticket_offered=ticket_offered)
        validate_observation(value, key[1], key[2])
        destinations = [x for x in self._destinations if x != name] + [name]
        destinations = destinations[-self.max_destinations:]
        groups = {k: deepcopy(v) for k, v in self._groups.items() if k[0] in destinations}
        groups[key] = (groups.get(key, []) + [deepcopy(value)])[-self.window:]
        self._destinations, self._groups, self.last_sequence = destinations, groups, sequence
        return dict(key=list(key), restart_without_token=token_rejected,
                    reuse_connection=False if token_rejected else None)

    def to_dict(self):
        return dict(version=STATE_VERSION, max_destinations=self.max_destinations, window=self.window,
                    last_sequence=self.last_sequence,
                    destinations=[dict(name=name, groups=[dict(address=k[1], tls=k[2], observations=deepcopy(self._groups[k]))
                                                          for k in sorted(self._groups) if k[0] == name])
                                  for name in self._destinations])

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {'version', 'max_destinations', 'window', 'last_sequence', 'destinations'}:
            raise ValueError('invalid cache fields')
        if type(value['version']) is not int or value['version'] != STATE_VERSION:
            raise ValueError('unsupported cache version')
        cache = cls(max_destinations=value['max_destinations'], window=value['window'])
        integer('last_sequence', value['last_sequence'], -1, MAX_SEQUENCE)
        if not isinstance(value['destinations'], list) or len(value['destinations']) > cache.max_destinations:
            raise ValueError('invalid destination list')
        sequences = set()
        for entry in value['destinations']:
            if not isinstance(entry, dict) or set(entry) != {'name', 'groups'}:
                raise ValueError('invalid destination fields')
            name = destination(entry['name'])
            if name in cache._destinations:
                raise ValueError('duplicate destination')
            if not isinstance(entry['groups'], list) or not 1 <= len(entry['groups']) <= len(ADDRESSES) * len(TLS_KINDS):
                raise ValueError('invalid groups')
            cache._destinations.append(name)
            for group in entry['groups']:
                if not isinstance(group, dict) or set(group) != {'address', 'tls', 'observations'}:
                    raise ValueError('invalid group fields')
                if group['address'] not in ADDRESSES or group['tls'] not in TLS_KINDS:
                    raise ValueError('invalid group')
                key = (name, group['address'], group['tls'])
                if key in cache._groups:
                    raise ValueError('duplicate group')
                rows = group['observations']
                if not isinstance(rows, list) or not 1 <= len(rows) <= cache.window:
                    raise ValueError('invalid observation window')
                previous = -1
                for row in rows:
                    validate_observation(row, key[1], key[2])
                    seq = row['sequence']
                    if seq <= previous or seq in sequences or seq > value['last_sequence']:
                        raise ValueError('invalid observation sequence')
                    previous = seq
                    sequences.add(seq)
                cache._groups[key] = deepcopy(rows)
        if (max(sequences) if sequences else -1) != value['last_sequence']:
            raise ValueError('last sequence is not represented')
        latest = [max(row['sequence'] for k, rows in cache._groups.items() if k[0] == name for row in rows)
                  for name in cache._destinations]
        if latest != sorted(latest):
            raise ValueError('destination LRU order disagrees with observations')
        cache.last_sequence = value['last_sequence']
        return cache
