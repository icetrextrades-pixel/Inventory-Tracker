"""Pinned GitHub updater. No packages; replaces program files, never shop records."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

REPO = 'icetrextrades-pixel/Inventory-Tracker'
BRANCH = 'family-shop-offline'
FILES = ('app.py', 'ledger.py', 'updater.py', 'start_shop.bat', 'setup_shortcut.vbs', 'README.md')
MAX_FILE = 2 * 1024 * 1024


def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'FamilyShop-Updater','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=30) as response:
        data=response.read(MAX_FILE+1)
    if len(data)>MAX_FILE:raise ValueError('Update file exceeds size limit.')
    return data


def remote_version():
    data=json.loads(fetch(f'https://api.github.com/repos/{REPO}/commits/{BRANCH}'))
    sha=data['sha']
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Invalid update version.')
    return sha


def stage_update(destination, sha):
    """Download all files before touching the installed app; validate Git blob hashes."""
    tree=json.loads(fetch(f'https://api.github.com/repos/{REPO}/git/trees/{sha}?recursive=1'))
    if tree.get('truncated'):raise ValueError('Incomplete update listing.')
    entries={r['path']:r for r in tree['tree']}
    for name in FILES:
        entry=entries.get('offline_shop/'+name)
        if not entry or entry['type']!='blob' or entry.get('size',0)>MAX_FILE:raise ValueError('Missing or invalid update file: '+name)
        data=fetch(f'https://raw.githubusercontent.com/{REPO}/{sha}/offline_shop/{name}')
        actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if actual!=entry['sha']:raise ValueError('Update integrity check failed: '+name)
        if name.endswith('.py'):compile(data,name,'exec')
        (destination/name).write_bytes(data)
    (destination/'installed-version.txt').write_text(sha,encoding='ascii')


def install_staged(root,stage,rollback):
    """Keep recovery copies and roll back if any replacement fails."""
    names=(*FILES,'installed-version.txt')
    existing=[];replaced=[]
    rollback.mkdir(parents=True,exist_ok=True)
    for name in names:
        if (root/name).exists():shutil.copy2(root/name,rollback/name);existing.append(name)
    try:
        for name in names:
            os.replace(stage/name,root/name);replaced.append(name)
    except Exception:
        for name in reversed(replaced):
            if name in existing:shutil.copy2(rollback/name,root/name)
            else:(root/name).unlink(missing_ok=True)
        raise


def run_update(root,sha,backup):
    import sqlite3
    # Back up every shop before updating shared program files.
    sources=[backup.parent/'shop.sqlite3']+sorted((backup.parent/'shops').glob('*/shop.sqlite3'))
    for source_path in sources:
        if not source_path.exists():continue
        target_path=backup if source_path.parent==backup.parent else backup.with_name(backup.stem+'-'+source_path.parent.name+'.sqlite3')
        with sqlite3.connect(source_path) as source,sqlite3.connect(target_path) as target:source.backup(target)
    with tempfile.TemporaryDirectory(prefix='.shop-update-',dir=root) as temp:
        stage=Path(temp)
        stage_update(stage,sha)
        install_staged(root,stage,root/'update-recovery')


def main():
    """Runs as a separate process after the app releases its database."""
    import tkinter as tk
    from tkinter import messagebox
    window=tk.Tk();window.withdraw()
    root=Path(__file__).resolve().parent
    data=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'FamilyShop'
    data.mkdir(parents=True,exist_ok=True)
    lock=root/'.update-lock'
    locked=False
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd);locked=True
        sha=sys.argv[1]
        if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Invalid version.')
        from datetime import datetime
        backup=data/('before-update-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')
        run_update(root,sha,backup)
        messagebox.showinfo('Update complete','Mutowei Investments has been updated. Your records were backed up. The app will now reopen.')
    except FileExistsError:
        messagebox.showerror('Update already running','Another update is running. If a previous update was interrupted, close all Mutowei Investments windows and remove .update-lock from the app folder.')
        return
    except Exception as exc:
        messagebox.showerror('Update failed',f'{exc}\n\nYour records have not been replaced. The app will reopen. Try again when internet is available.')
    finally:
        if locked:lock.unlink(missing_ok=True)
    subprocess.Popen([sys.executable,str(root/'app.py')],cwd=root)
    window.destroy()


if __name__=='__main__':main()
