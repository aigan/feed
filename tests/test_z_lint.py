import subprocess

from config import ROOT


def test_ruff_lint():
    result = subprocess.run(
        ['ruff', 'check', 'lib', 'tests'],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, f'ruff violations:\n{result.stdout}'
