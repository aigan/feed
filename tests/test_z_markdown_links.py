import os
import re

from config import ROOT

LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


def collect_md_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in {'.git', '.venv', 'old-venv', 'data', 'var', '__pycache__'}]
        for f in filenames:
            if f.endswith('.md'):
                yield os.path.join(dirpath, f)


def collect_py_files():
    for subdir in ['lib', 'bin']:
        base = os.path.join(ROOT, subdir)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in {'__pycache__'}]
            for f in filenames:
                if f.endswith('.py'):
                    yield os.path.join(dirpath, f)


def validate_links(filepath, lines):
    violations = []
    file_dir = os.path.dirname(filepath)
    for lineno, line in enumerate(lines, 1):
        for match in LINK_RE.finditer(line):
            text, target = match.group(1), match.group(2)
            if target.startswith(('http://', 'https://', '#', 'mailto:')):
                continue
            resolved = os.path.normpath(os.path.join(file_dir, target))
            if not os.path.exists(resolved):
                rel = os.path.relpath(filepath, ROOT)
                violations.append(f'  {rel}:{lineno}  [{text}]({target})  -> {resolved}')
    return violations


def test_markdown_relative_links():
    violations = []
    for filepath in collect_md_files():
        with open(filepath) as f:
            violations.extend(validate_links(filepath, f.readlines()))
    assert not violations, 'Broken relative links in .md files:\n' + '\n'.join(violations)


def test_python_comment_links():
    violations = []
    for filepath in collect_py_files():
        with open(filepath) as f:
            comment_lines = []
            for lineno, line in enumerate(f, 1):
                stripped = line.lstrip()
                if stripped.startswith('#'):
                    comment_lines.append((lineno, line))
        file_dir = os.path.dirname(filepath)
        for lineno, line in comment_lines:
            for match in LINK_RE.finditer(line):
                text, target = match.group(1), match.group(2)
                if target.startswith(('http://', 'https://', '#', 'mailto:')):
                    continue
                resolved = os.path.normpath(os.path.join(file_dir, target))
                if not os.path.exists(resolved):
                    rel = os.path.relpath(filepath, ROOT)
                    violations.append(f'  {rel}:{lineno}  [{text}]({target})  -> {resolved}')
    assert not violations, 'Broken relative links in .py comments:\n' + '\n'.join(violations)
