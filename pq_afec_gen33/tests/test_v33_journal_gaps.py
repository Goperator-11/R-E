import json

import pytest

from experiments.v33.lib import blocks
from test_v33_devbed_blocks import create, entries, rehash_record, reopen


def _three_lines(tmp_path):
    journal = create(tmp_path)
    schedule = journal.expected_units
    journal.record_block(entries(schedule[:2]))
    journal.record_block(entries(schedule[2:4]))
    return journal


def test_rewritten_middle_record_breaks_chain_even_when_it_rehashes(tmp_path):
    journal = _three_lines(tmp_path)
    lines = journal.path.read_bytes().splitlines(keepends=True)
    assert len(lines) == 3
    value = json.loads(lines[1])
    value["data"]["units"][0]["payload"]["rows"][1]["ok"] = True
    lines[1] = rehash_record(value)
    journal.path.write_bytes(b"".join(lines))
    with pytest.raises(blocks.JournalError, match="chain"):
        reopen(journal)


def test_record_with_rehashed_wrong_previous_digest_is_rejected(tmp_path):
    journal = _three_lines(tmp_path)
    lines = journal.path.read_bytes().splitlines(keepends=True)
    value = json.loads(lines[2])
    value["previous_sha256"] = "f" * 64
    lines[2] = rehash_record(value)
    journal.path.write_bytes(b"".join(lines))
    with pytest.raises(blocks.JournalError, match="chain"):
        reopen(journal)
