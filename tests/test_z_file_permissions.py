import os
import stat
import subprocess

from config import ROOT

MY_UID = os.getuid()


def collect_files():
    result = subprocess.run(
        ['git', 'ls-files'],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    for relpath in result.stdout.splitlines():
        filepath = os.path.join(ROOT, relpath)
        if os.path.dirname(relpath) == '' and os.path.basename(relpath).startswith('.'):
            continue
        if os.path.isfile(filepath) and os.stat(filepath).st_uid == MY_UID:
            yield filepath


def test_group_read_write_permissions():
    violations = []
    for filepath in collect_files():
        mode = os.stat(filepath).st_mode
        if not (mode & stat.S_IRGRP and mode & stat.S_IWGRP):
            rel = os.path.relpath(filepath, ROOT)
            violations.append(f'  {rel}  ({oct(mode)})  fix: chmod g+rw')
    assert not violations, 'Files missing group rw:\n' + '\n'.join(violations)


def test_group_matches_user_permissions():
    violations = []
    for filepath in collect_files():
        mode = os.stat(filepath).st_mode
        user_r = bool(mode & stat.S_IRUSR)
        user_w = bool(mode & stat.S_IWUSR)
        group_r = bool(mode & stat.S_IRGRP)
        group_w = bool(mode & stat.S_IWGRP)
        if user_r != group_r or user_w != group_w:
            rel = os.path.relpath(filepath, ROOT)
            violations.append(f'  {rel}  ({oct(mode)})  fix: chmod g=u')
    assert not violations, 'Files where group bits differ from user:\n' + '\n'.join(violations)
