from pathlib import Path
import subprocess

import pytest

from experiments.v33.lib import arms, transport
from test_v33_devbed_transport import fixed_unit, runtime


def _client_with_rows(fake, count):
    original = fake.run

    def run(command, **kwargs):
        if "-n" not in command:
            return original(command, **kwargs)
        kwargs["stdout"].write(b'{"ok":true,"ms":50}\n' * count)
        Path(command[command.index("-stats") + 1]).write_text('{"trials":1}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)
    return run


@pytest.mark.parametrize("delta", [-1, 1])
def test_client_row_count_mismatch_is_not_a_complete_unit(runtime, delta):
    backend, fake, plan = runtime
    unit = fixed_unit(plan)
    backend.run = _client_with_rows(fake, unit["rows_expected"] + delta)
    with pytest.raises(transport.TransportError, match="행 수 불일치") as error:
        backend.run_unit(unit)
    assert error.value.payload["client_rc"] == 0
    assert "rows" not in error.value.payload
    assert fake.processes[0].terminated


@pytest.mark.parametrize("task,arm,expected", [("M0", "m4L3", 380), ("X9", "mlkem_off", 1230)])
def test_client_timeout_covers_every_planned_connection(runtime, task, arm, expected):
    backend, fake, plan = runtime
    unit = fixed_unit(plan, task, arm)
    seen = {}
    original = fake.run

    def run(command, **kwargs):
        if "-n" in command:
            seen["timeout"] = kwargs["timeout"]
        return original(command, **kwargs)
    backend.run = run
    backend.run_unit(unit)
    assert seen["timeout"] == expected
    assert seen["timeout"] >= 10 * unit["connections"]


def test_certificate_is_shared_by_every_arm_of_a_cell_and_not_across_cells(runtime):
    backend, fake, plan = runtime
    cell_units = [unit for unit in arms.iter_units(plan, "M0") if unit["cell"] == "bigcert_l2"]
    assert len({unit["arm"] for unit in cell_units}) == 6
    results = [backend.prepare_certificate(unit) for unit in cell_units]
    assert {Path(item["path"]).name for item in results} == {"M0_bigcert_l2_cert_16000.pem"}
    assert sum("certgen" in call for call in fake.calls) == 1
    other = next(unit for unit in arms.iter_units(plan, "M0") if unit["cell"] == "bigcert_l15")
    assert Path(backend.prepare_certificate(other)["path"]).name == "M0_bigcert_l15_cert_16000.pem"
    assert sum("certgen" in call for call in fake.calls) == 2
