#from pathlib import Path
import os
from pathlib import Path

PROJECT_ROOT = os.environ.get('PROJECT_ROOT')

if PROJECT_ROOT is None:
    raise ValueError("PROJECT_ROOT environment variable is not set")

ROOT = Path(PROJECT_ROOT);

if not ROOT.exists():
    raise ValueError(f"PROJECT_ROOT points to non-existent path: '{ROOT}'")
