import sys
sys.dont_write_bytecode=True
import argparse
import hashlib
import json
import posixpath
import subprocess
from pathlib import Path

SEALED_COMMIT="4f26a51676c8429d778f549c821c75bd7dd37d8f"

def reader(root,ref):
    if ref is None:
        def read(rel):
            path=root/rel
            return path.read_bytes() if path.is_file() else None
        return read
    def read(rel):
        p=subprocess.run(["git","-C",str(root),"cat-file","blob",f"{ref}:{rel}"],capture_output=True)
        return p.stdout if p.returncode==0 else None
    return read

def verify(root,ref):
    read=reader(root,ref)
    rows=[]
    seals=[]
    for folder,name in (("pq_afec_gen31","SEAL_stage3.json"),("pq_afec_gen3","SEAL_stage2.json"),("pq_afec_gen3","SEAL_stage0.json"),("pq_afec_gen3","SEAL_m1confirm.json")):
        raw=read(f"{folder}/g3/{name}")
        if raw is None:
            raise FileNotFoundError(f"{folder}/g3/{name} at {ref or 'worktree'}")
        data=json.loads(raw.decode("utf-8"))
        part=[]
        for group in ("sha256","also_recorded_sha256"):
            for rel,wanted in data.get(group,{}).items():
                full=posixpath.normpath(posixpath.join(folder,rel))
                if not full.startswith(folder+"/"):
                    raise ValueError("seal path leaves generation folder")
                blob=read(full)
                actual=hashlib.sha256(blob).hexdigest() if blob is not None else None
                part.append(dict(generation=folder,seal=name,group=group,path=rel,expected=wanted,actual=actual,match=actual==wanted))
        rows.extend(part)
        seals.append(dict(generation=folder,seal=name,seal_sha256=hashlib.sha256(raw).hexdigest(),files=len(part),matches=sum(x["match"] for x in part),sha256_section_files=sum(x["group"]=="sha256" for x in part)))
    return dict(status="PASS" if rows and all(x["match"] for x in rows) else "FAIL",source=ref or "worktree",scope="tracked_relative_seal_and_also_recorded_files",files=len(rows),matches=sum(x["match"] for x in rows),sha256_section_files=sum(x["group"]=="sha256" for x in rows),seals=seals,rows=rows)

def main():
    parser=argparse.ArgumentParser(description="Check SEAL_*.json hashes against the sealed source bytes. By default the bytes are read from the commit before comment removal.")
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ref",default=SEALED_COMMIT)
    parser.add_argument("--worktree",action="store_true")
    args=parser.parse_args()
    result=verify(args.root.resolve(),None if args.worktree else args.ref)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["status"]=="PASS" else 1

if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
