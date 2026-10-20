"""Check the publishable HEAD and historical secret values without exposing them."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
GIT=shutil.which('git') or r'C:\Program Files\Git\cmd\git.exe'


def git(*args):
    return subprocess.check_output([GIT,*args],cwd=ROOT)


def known_secrets():
    values=[]
    for key,value in dotenv_values(ROOT/'.env').items():
        if value and ('KEY' in key or 'SECRET' in key or 'PASSWORD' in key):
            values.append(value.encode())
    access=ROOT/'local-access.txt'
    if access.exists():
        for line in access.read_text(encoding='utf-8').splitlines():
            if line.startswith('Passwort: '):
                values.append(line.split(': ',1)[1].encode())
    return values


def protected(path):
    name=Path(path).name
    if name.startswith('.env') and name!='.env.example':
        return True
    if path in ('local-access.txt','docs/MASTER_PROMPT.md'):
        return True
    if any(path.startswith(p) for p in ('data/','logs/','backups/')) and name!='.gitkeep':
        return True
    return path.endswith(('.sqlite3','.sqlite3-wal','.sqlite3-shm','.pfx','.pem'))


def check():
    secrets=known_secrets()
    pattern=re.compile(rb'(?:sk-proj-[A-Za-z0-9_-]{25,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})')
    findings=[]
    head_paths=git('ls-tree','-r','--name-only','HEAD').decode().splitlines()
    for path in head_paths:
        if protected(path):
            findings.append({'path':path,'reason':'protected local file is tracked in HEAD'})
    count=0
    for entry in git('rev-list','--objects','--all').decode().splitlines():
        parts=entry.split(' ',1)
        if len(parts)!=2:
            continue
        oid,path=parts
        if git('cat-file','-t',oid).strip()!=b'blob':
            continue
        content=git('cat-file','blob',oid)
        count+=1
        if any(secret in content for secret in secrets) or pattern.search(content):
            findings.append({'path':path,'object':oid,'reason':'secret detected; value redacted'})
    return {'tracked_files':len(head_paths),'historical_blobs_checked':count,'findings':findings}


if __name__=='__main__':
    report=check()
    print(json.dumps(report,ensure_ascii=True))
    raise SystemExit(1 if report['findings'] else 0)
