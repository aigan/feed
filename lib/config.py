import os
from pathlib import Path

PROJECT_ROOT = os.environ.get('PROJECT_ROOT')

if PROJECT_ROOT is None:
    raise ValueError("PROJECT_ROOT environment variable is not set")

ROOT = Path(PROJECT_ROOT)

if not ROOT.exists():
    raise ValueError(f"PROJECT_ROOT points to non-existent path: '{ROOT}'")

DATA_DIR = Path(os.environ.get('DATA_DIR', str(ROOT / "data")))

# Chrome config — only needed for bin/web/ scripts
CHROME_USER_DIR = os.environ.get('CHROME_USER_DIR')
CHROME_PROFILE = os.environ.get('CHROME_PROFILE')
if CHROME_USER_DIR:
    CHROME_USER_DIR = Path(CHROME_USER_DIR).expanduser()
