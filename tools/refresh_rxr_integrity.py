"""Refresh approved RxR/build pins after protected-asset validation, never before it."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def gitblob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def main():
    profile=ROOT/'provenance/rxr_profile_integrity.json'
    value=json.loads(profile.read_text(encoding='utf-8'))
    paths={row['path'] for row in value['files']}
    paths.update({'host/rxr_retrieval.py','host/rxr_assets.py','provenance/rxr_training_sources.json'})
    for role in ('generator','reviewer'):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/role/'templates'/'RxR'/'train').glob('*.json'))
    value['files']=[dict(path=p,git_blob_sha1=gitblob((ROOT/p).read_bytes())) for p in sorted(paths)]
    value['file_count']=len(value['files'])
    profile.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files={}
    for path in sorted(ROOT.rglob('*')):
        if (not path.is_file() or '.git' in path.parts or '__pycache__' in path.parts
                or path.suffix=='.pyc' or path.name=='FILE_HASHES.json'):
            continue
        files[path.relative_to(ROOT).as_posix()]='gitblob-sha1:'+gitblob(path.read_bytes())
    (ROOT/'FILE_HASHES.json').write_text(json.dumps(files,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'source_files':len(files),'rxr_pinned_assets':len(paths)}))

if __name__=='__main__':
    main()
