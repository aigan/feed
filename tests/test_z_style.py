import os
import re

from config import ROOT

SEMICOLON_RE = re.compile(r';\s*$')


def collect_py_files():
    for subdir in ['lib', 'bin', 'tests']:
        base = os.path.join(ROOT, subdir)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in {'__pycache__', '.pytest_cache'}]
            for f in filenames:
                if f.endswith('.py'):
                    yield os.path.join(dirpath, f)


def test_no_semicolons():
    violations = []
    for filepath in collect_py_files():
        with open(filepath) as f:
            for lineno, line in enumerate(f, 1):
                stripped = line.lstrip()
                if stripped.startswith('#'):
                    continue
                if SEMICOLON_RE.search(line):
                    rel = os.path.relpath(filepath, ROOT)
                    violations.append(f'  {rel}:{lineno}  {line.rstrip()}')
    assert not violations, 'Trailing semicolons:\n' + '\n'.join(violations)


def test_no_trailing_whitespace():
    violations = []
    for filepath in collect_py_files():
        with open(filepath) as f:
            for lineno, line in enumerate(f, 1):
                if re.search(r'[ \t]+$', line.rstrip('\n')):
                    rel = os.path.relpath(filepath, ROOT)
                    violations.append(f'  {rel}:{lineno}')
    assert not violations, 'Trailing whitespace:\n' + '\n'.join(violations)


def test_no_blank_lines_at_eof():
    violations = []
    for filepath in collect_py_files():
        with open(filepath, 'rb') as f:
            content = f.read()
        if content.endswith(b'\n\n'):
            rel = os.path.relpath(filepath, ROOT)
            violations.append(f'  {rel}')
    assert not violations, 'Blank lines at end of file:\n' + '\n'.join(violations)
