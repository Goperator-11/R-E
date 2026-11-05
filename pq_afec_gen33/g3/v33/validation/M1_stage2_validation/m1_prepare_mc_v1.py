import sys
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding="utf-8")
import ast
from pathlib import Path

root=Path(r"C:\dev\pq_afec_gen33\experiments\v33")

def copy(name,target,replacements):
    text=(root/name).read_text(encoding="utf-8")
    for old,new in replacements:
        assert old in text,old
        text=text.replace(old,new)
    compile(text,str(root/target),"exec")
    with (root/target).open("x",encoding="utf-8",newline="\n") as f:f.write(text)

copy("oracle.py","oracle_m1.py",[
    ("from .worldsim import", "from .worldsim_m1 import"),
    ('("oracle.py", "worldsim.py", "worldparams.json")', '("oracle_m1.py", "worldsim_m1.py", "worldparams_m1.json", "world_receiver_m1.py")'),
    ('sources["worldsim.py"]','sources["worldsim_m1.py"]')])
copy("bench_oracles.py","bench_oracles_m1.py",[
    ('from experiments.v33 import bench, oracle','from experiments.v33 import bench, oracle_m1 as oracle'),
    ('("oracle.py", "worldsim.py", "worldparams.json")','("oracle_m1.py", "worldsim_m1.py", "worldparams_m1.json", "world_receiver_m1.py")'),
    ('"bench_oracles.py"','"bench_oracles_m1.py"')])
copy("bench_action_pool.py","bench_action_pool_m1.py",[
    ('from experiments.v33 import bench, bench_oracles, oracle','from experiments.v33 import bench, bench_oracles_m1 as bench_oracles, oracle_m1 as oracle')])

source=(root/"bench_learning_report.py").read_text(encoding="utf-8")
tree=ast.parse(source)
names={"family_manifest","job_set","receipt_pairs","validate_pool_locked"}
blocks=[ast.get_source_segment(source,node) for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
assert len(blocks)==len(names)
prefix='''from pathlib import Path
import re
from experiments.v33 import bench, bench_action_pool_m1 as pool, bench_oracles_m1 as bench_oracles, bench_report
from experiments.v33.bench_learning_report import equal, check_files

STAMP = r"[0-9]{20}_[0-9a-f]{32}"

'''
with (root/"m1_pool_validation.py").open("x",encoding="utf-8",newline="\n") as f:f.write(prefix+"\n\n\n".join(blocks)+"\n")

copy("bench_j7_family.py","bench_m1_family.py",[
    ('bench_j7 as collector','bench_m1 as collector'),
    ('bench_action_pool as pool','bench_action_pool_m1 as pool'),
    ('from experiments.v33 import bench_learning_report as legacy, bench_action_pool_m1 as pool, bench_oracles',
     'from experiments.v33 import bench_learning_report as legacy, bench_action_pool_m1 as pool, bench_oracles\nfrom experiments.v33 import m1_pool_validation as validation'),
    ('padfec.v33.j7_action_family/1','padfec.v33.m1_action_family/1'),
    ('5f417689ea9d677e9153ba88246c20c38da8caf3bae4dabd4e67b088fa039d81','5be8bd6cb35a9d309c7c762a0ee0a2ff62e068c0f689875b4e0942fe2decf591'),
    ('["wire39"]','["off"]'),
    ('    original = plan["protocols"]["off"]','    original = bench.load_protocol(Path(plan["original_protocol"]))'),
    ('legacy.family_manifest','validation.family_manifest'),
    ('"J7 complete 2x2x3 factorial; every trace row validated"','"M1 complete 2x2x3 factorial and original v31/v32; every trace row validated"')])
print("created oracle, job adapter, pool, validation and family copies")
