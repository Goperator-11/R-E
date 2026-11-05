import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding='utf-8')
import ast
import hashlib
from pathlib import Path

RUNS = Path(r'C:\dev\codex_handoff\v33\runs')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
family_sha = sha(RUNS / 'J1_joint_action_family_v1.json')
value = (RUNS / 'l3_final_bundle_v2.py').read_text(encoding='utf-8')
value = value.replace('L3','J1').replace('l3','j1')
for old,new in (
    ('ea77279f815caadde485d35b28a1caae7b29d34154fd5a2d4a7782f98b4d81ee',sha(RUNS/'j1_joint_artifact_check_v1.py')),
    ('f149de0bdec682502bd3909738d2e8699c1e17b0ed4d217ec4d2b12dd3b46653',sha(RUNS/'j1_findings_extract_v1.py')),
    ('3e31108f94fe693d60507e213f6a6e4f77876479675a63f65343122f921262ad',family_sha),
    ('3300','3000'),('== 165','== 150'),('== 90','== 75'),('1800','1500'),
    ('findings["provenance"]["check_sha256"]','findings["checker_sha256"]'),
    ('findings["provenance"]["report_sha256"]','findings["report_sha256"]'),
    ('findings["provenance"]["extractor_sha256"]','findings["script_sha256"]'),
    ('"J1_findings_v1.md"','"J1_bench.md"'),
    ('"iter018_*", "iter019_*"','"iter020_*", "iter021_*", "iter022_*"')
):
    assert old in value, old
    value = value.replace(old,new)
ast.parse(value)
path = RUNS / 'j1_final_bundle_v1.py'
with path.open('x',encoding='utf-8',newline='\n') as stream:stream.write(value)
print(sha(path))
