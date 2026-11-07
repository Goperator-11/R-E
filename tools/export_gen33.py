import sys
sys.dont_write_bytecode=True
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path, PurePosixPath

TOKEN=re.compile(rb"g3/v33/validation/([A-Za-z0-9_.-]+)/")
TEST_FILE=re.compile(r"tests/[^/]+\.py")
RULE_KEYS={"validation_prefix","bundles_py_only","bundles_all","exclude_prefix"}


class Refused(Exception):
    pass


def size_rules():
    path=Path(__file__).resolve().with_name("precommit_size.py")
    spec=importlib.util.spec_from_file_location("precommit_size",path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.LIMIT,module.PRIVATE_KEY


def git(where,*args,data=None):
    return subprocess.run(["git","-C",str(where),*args],input=data,stdout=subprocess.PIPE,check=True).stdout


def load_rule(path):
    raw=path.read_bytes()
    rule=json.loads(raw.decode("utf-8"))
    if not isinstance(rule,dict) or set(rule)!=RULE_KEYS:
        raise Refused("rule keys must be "+", ".join(sorted(RULE_KEYS)))
    if not isinstance(rule["validation_prefix"],str) or not rule["validation_prefix"].endswith("/"):
        raise Refused("validation_prefix must be a folder prefix")
    for key in ("bundles_py_only","bundles_all","exclude_prefix"):
        if not isinstance(rule[key],list) or not all(isinstance(x,str) and x for x in rule[key]):
            raise Refused(key+" must be a list of names")
    return rule,hashlib.sha256(raw).hexdigest()


def selected(rule,path):
    if any(path.startswith(prefix) for prefix in rule["exclude_prefix"]):
        return False
    prefix=rule["validation_prefix"]
    if not path.startswith(prefix):
        return True
    bundle,sep,_=path[len(prefix):].partition("/")
    if not sep:
        return False
    if bundle in rule["bundles_all"]:
        return True
    return bundle in rule["bundles_py_only"] and path.endswith(".py")


def tree(src,rev):
    rows=[]
    for item in git(src,"ls-tree","-r","-l","-z","--full-tree",rev).split(b"\0"):
        if not item:
            continue
        meta,name=item.split(b"\t",1)
        mode,kind,sha,size=meta.split()
        path=name.decode("utf-8")
        parts=PurePosixPath(path).parts
        if kind!=b"blob" or mode not in (b"100644",b"100755"):
            raise Refused("unsupported tree entry: "+path)
        if PurePosixPath(path).is_absolute() or any(part in ("",".","..") for part in parts):
            raise Refused("unsafe path: "+path)
        rows.append(dict(path=path,mode=mode.decode("ascii"),blob=sha.decode("ascii"),size=int(size)))
    return rows


def text_unset(src,rev,paths):
    if not paths:
        return {}
    data=b"".join(path.encode("utf-8")+b"\0" for path in paths)
    parts=git(src,"check-attr","--source="+rev,"-z","--stdin","text",data=data).split(b"\0")
    result={}
    for index in range(0,len(parts)-2,3):
        result[parts[index].decode("utf-8")]=parts[index+2]==b"unset"
    if set(result)!=set(paths):
        raise Refused("check-attr did not report every path")
    return result


def blobs(src,rows):
    with subprocess.Popen(["git","-C",str(src),"cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as process:
        for row in rows:
            process.stdin.write((row["blob"]+"\n").encode("ascii"))
            process.stdin.flush()
            header=process.stdout.readline().split()
            if len(header)!=3 or header[0].decode("ascii")!=row["blob"] or header[1]!=b"blob" or int(header[2])!=row["size"]:
                raise Refused("blob identity changed: "+row["path"])
            raw=process.stdout.read(row["size"])
            if len(raw)!=row["size"] or process.stdout.read(1)!=b"\n":
                raise Refused("incomplete blob: "+row["path"])
            yield row,raw
        process.stdin.close()
        if process.wait()!=0:
            raise Refused("git cat-file failed")


def problems(src,rev,rule,rows):
    limit,private_key=size_rules()
    known=set(rule["bundles_py_only"])|set(rule["bundles_all"])
    unset=text_unset(src,rev,[row["path"] for row in rows])
    found=[]
    for row in rows:
        if row["size"]>limit:
            found.append(dict(kind="oversize",path=row["path"],bytes=row["size"]))
    for row,raw in blobs(src,[row for row in rows if row["size"]<=limit]):
        if private_key.search(raw):
            found.append(dict(kind="private_key",path=row["path"]))
        if TEST_FILE.fullmatch(row["path"]):
            for bundle in sorted({match.group(1).decode("utf-8","replace") for match in TOKEN.finditer(raw)}-known):
                found.append(dict(kind="bundle_outside_rule",path=row["path"],bundle=bundle))
        if not unset[row["path"]] and b"\0" not in raw[:8000] and b"\r\n" in raw:
            found.append(dict(kind="crlf_in_text_blob",path=row["path"]))
    return found


def destination(dest,src):
    dest=dest.resolve()
    src=src.resolve()
    if dest.name!="pq_afec_gen33":
        raise Refused("destination folder must be named pq_afec_gen33")
    if not dest.parent.is_dir():
        raise Refused("destination parent does not exist")
    try:
        top=Path(git(dest.parent,"rev-parse","--show-toplevel").decode("utf-8").strip()).resolve()
    except subprocess.CalledProcessError:
        raise Refused("destination is not inside a git worktree")
    if dest==top or not dest.is_relative_to(top):
        raise Refused("destination must be a folder inside the git worktree")
    if (dest/".git").exists():
        raise Refused("destination is its own repository")
    if dest==src or dest.is_relative_to(src) or src.is_relative_to(dest):
        raise Refused("destination overlaps the source repository")
    return dest,top


def writable(function,path,_error):
    os.chmod(path,stat.S_IWRITE)
    function(path)


def export(src,rev,dest,rule_path):
    rule,rule_sha=load_rule(rule_path)
    commit=git(src,"rev-parse","--verify",rev+"^{commit}").decode("ascii").strip()
    dest,top=destination(dest,src)
    rows=[row for row in tree(src,commit) if selected(rule,row["path"])]
    found=problems(src,commit,rule,rows)
    if found:
        return 1,dict(status="FAIL",source_rev=commit,problems=found)
    if dest.exists():
        shutil.rmtree(dest,onexc=writable)
    dest.mkdir()
    for row,raw in blobs(src,rows):
        target=dest.joinpath(*PurePosixPath(row["path"]).parts)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
    manifest=dict(source_rev=commit,rule_sha256=rule_sha,rule=rule,dest=dest.relative_to(top).as_posix(),file_count=len(rows),executable=[row["path"] for row in rows if row["mode"]=="100755"],files={row["path"]:row["blob"] for row in rows})
    out=top/"docs"/"EXPORT_gen33.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes((json.dumps(manifest,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
    return 0,dict(status="PASS",source_rev=commit,rule_sha256=rule_sha,file_count=len(rows),dest=dest.relative_to(top).as_posix(),manifest=out.relative_to(top).as_posix())


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--src",type=Path,required=True)
    parser.add_argument("--rev",required=True)
    parser.add_argument("--dest",type=Path,required=True)
    parser.add_argument("--rule",type=Path,default=Path(__file__).resolve().with_name("gen33_export_rule.json"))
    args=parser.parse_args(argv)
    try:
        code,result=export(args.src,args.rev,args.dest,args.rule)
    except (Refused,subprocess.CalledProcessError,OSError,ValueError) as exc:
        print(json.dumps(dict(status="ERROR",error=str(exc)),ensure_ascii=False))
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return code


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
