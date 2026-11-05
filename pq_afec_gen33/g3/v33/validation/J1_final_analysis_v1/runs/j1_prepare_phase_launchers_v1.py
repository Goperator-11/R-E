import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding='utf-8')
import ast
import hashlib
import json
from pathlib import Path

RUNS = Path(r'C:\dev\codex_handoff\v33\runs')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
family_path = RUNS / 'J1_joint_action_family_v1.json'
family = read(family_path)
end = read(RUNS / 'J1_joint_plan_v1.finished.json')
assert end['status'] == 'complete' and end['exit_code'] == 0
assert end['published_outputs_sha256'][str(family_path)] == sha(family_path)
assert family['role_run_counts'] == {'baseline':600,'l1':900,'j1':900,'cost':600}
assert len(family['manifest']['raw_run_identities']) == 3000
old_driver = 'bb8df767195787b5eb0d07747a789a2cdd507fdd6c67e199197059da40c7d0b4'
old_family = '3e31108f94fe693d60507e213f6a6e4f77876479675a63f65343122f921262ad'
outputs = {}
for name in ('launch_l3_joint_run_v1.ps1','launch_l3_joint_report_v1.ps1','launch_l3_validation_v1.ps1','l3_joint_progress_v1.py'):
    value = (RUNS / name).read_text(encoding='utf-8-sig')
    value = value.replace('L3','J1').replace('l3','j1').replace(old_driver,sha(RUNS/'j1_joint_driver_v1.py')).replace(old_family,sha(family_path))
    value = value.replace('551d3f61fa2b4c9678b00972ee7a59c15fc4c2fc2be1331206ddf5e1cc59679e',sha(RUNS/'j1_validation_driver_v1.py'))
    value = value.replace(' -or $family.role_run_counts.guard -ne 300 -or $family.role_run_counts.record -ne 300 -or $family.role_run_counts.beta -ne 300',' -or $family.role_run_counts.cost -ne 600')
    value = value.replace('3300','3000')
    assert old_driver not in value and old_family not in value
    output = RUNS / name.replace('l3','j1')
    if output.suffix == '.py': ast.parse(value)
    with output.open('x',encoding='utf-8-sig' if output.suffix=='.ps1' else 'utf-8',newline='\n') as stream:stream.write(value)
    outputs[str(output)] = sha(output)
result = {'family_sha256':sha(family_path),'family_size':family['manifest']['evaluation_family_size'],'outputs_sha256':outputs,'script_sha256':sha(__file__)}
with (RUNS/'J1_phase_launcher_preparation_v1.json').open('x',encoding='utf-8',newline='\n') as stream:
    json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps(result))
