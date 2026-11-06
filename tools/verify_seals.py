import sys
sys.dont_write_bytecode=True
import argparse
import hashlib
import json
from pathlib import Path

def verify(root):
    rows=[]
    for folder,name in (("pq_afec_gen31","SEAL_stage3.json"),("pq_afec_gen3","SEAL_stage2.json"),("pq_afec_gen3","SEAL_stage0.json")):
        base=root/folder
        seal=base/"g3"/name
        data=json.loads(seal.read_text(encoding="utf-8"))
        for group in ("sha256","also_recorded_sha256"):
            for rel,wanted in data.get(group,{}).items():
                path=(base/rel).resolve()
                if not path.is_relative_to(base.resolve()):
                    raise ValueError("seal path leaves generation folder")
                actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
                rows.append(dict(generation=folder,seal=name,group=group,path=rel,expected=wanted,actual=actual,match=actual==wanted))
    return dict(status="PASS" if all(x["match"] for x in rows) else "FAIL",scope="tracked_relative_seal_and_also_recorded_files",files=len(rows),matches=sum(x["match"] for x in rows),rows=rows)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    result=verify(args.root.resolve())
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["status"]=="PASS" else 1

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
