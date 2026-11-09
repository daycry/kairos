"""Remove only a redundant, auto-discovered custom-agents declaration.

Default: read-only plan. --apply backs up the original beside opencode.json.
No plugin code, credentials, model settings or service state are changed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid
from urllib.parse import unquote, urlsplit


class RepairError(Exception): pass


def checked(path):
    path=Path(path).absolute()
    for part in (path,*path.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():
            raise RepairError('Linked configuration paths require manual review')
    return path


def read(path):
    path=checked(path)
    if path.stat().st_size>1_048_576:raise RepairError('Configuration exceeded the inspection limit')
    return path.read_bytes()


def target_entry(entry,directory,plugin):
    if not isinstance(entry,str) or entry.startswith('-'):return False
    if entry.startswith('file:'):
        url=urlsplit(entry)
        if url.netloc not in ('','localhost') or url.query or url.fragment:return False
        entry=unquote(url.path)
        if os.name=='nt' and re.match(r'^/[A-Za-z]:/',entry):entry=entry[1:]
    elif '://' in entry:return False
    candidate=Path(entry)
    if not candidate.is_absolute():candidate=directory/candidate
    return os.path.normcase(str(candidate.resolve()))==os.path.normcase(str(plugin.resolve()))


def plan(config_dir):
    directory=checked(config_dir)
    config=checked(directory/'opencode.json')
    before=read(config)
    try:data=json.loads(before.decode('utf-8-sig'))
    except (ValueError,UnicodeError):raise RepairError('Expected JSON configuration; JSONC requires manual review') from None
    if not isinstance(data,dict) or not isinstance(data.get('plugins',[]),list):raise RepairError('Unexpected plugin configuration')
    plugin=checked(directory/'plugins/custom-agents')
    package=json.loads(read(plugin/'package.json').decode('utf-8-sig'))
    source=read(plugin/'index.js').decode('utf-8-sig')
    if package.get('name')!='custom-agents-hooks' or not re.search(r'\bid\s*:\s*[\"\x27]custom-agents[\"\x27]',source):
        raise RepairError('Auto-discovered custom-agents identity was not verified')
    remove=[]
    for index,entry in enumerate(data.get('plugins',[])):
        candidate=entry.get('package') if isinstance(entry,dict) else entry
        if target_entry(candidate,directory,plugin):
            if not isinstance(entry,str):raise RepairError('Configured plugin options require manual reconciliation')
            remove.append(index)
    desired=dict(data)
    if remove:
        desired['plugins']=[value for index,value in enumerate(data['plugins']) if index not in remove]
        if not desired['plugins']:del desired['plugins']
    after=(json.dumps(desired,ensure_ascii=False,indent=2)+'\n').encode('utf-8') if remove else before
    return config,before,after,{'status':'repair_required' if remove else 'already_clean',
        'plugin_id':'custom-agents','redundant_entries':len(remove),'auto_discovered_plugin_preserved':True,
        'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest()}


def repair(config_dir,apply=False):
    config,before,after,result=plan(config_dir)
    if not apply or before==after:return dict(result,applied=False)
    identity=uuid.uuid4().hex
    backup=checked(config.with_name(config.name+'.kairos-before-'+identity+'.bak'))
    temporary=checked(config.with_name(config.name+'.kairos-'+identity+'.tmp'))
    if read(config)!=before:raise RepairError('Configuration changed concurrently; nothing replaced')
    # Exclusive files: never overwrite a previous backup or another process's temp.
    try:
        with backup.open('xb') as stream:
            stream.write(before);stream.flush();os.fsync(stream.fileno())
        with temporary.open('xb') as stream:
            stream.write(after);stream.flush();os.fsync(stream.fileno())
        mode=stat.S_IMODE(config.stat().st_mode)
        os.chmod(backup,mode);os.chmod(temporary,mode)
        if read(config)!=before:raise RepairError('Configuration changed concurrently; nothing replaced')
        temporary.replace(checked(config))
        if read(config)!=after:raise RepairError('Readback differs; inspect the preserved backup before retrying')
        return dict(result,status='repaired',applied=True,backup_file=backup.name,service_restarted=False)
    finally:
        try:temporary.unlink()
        except FileNotFoundError:pass


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--config-dir',default=str(Path.home()/'.config/opencode'))
    args=parser.parse_args(argv)
    try:
        print(json.dumps(repair(args.config_dir,args.apply),ensure_ascii=True,indent=2));return 0
    except Exception as error:
        print(json.dumps({'status':'failed','error_type':type(error).__name__,
            'message':str(error) if isinstance(error,RepairError) else 'Repair stopped; configuration and credentials are not printed.'}));return 1


if __name__=='__main__':sys.exit(main())
