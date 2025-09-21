#from pathlib import Path
import os
from pathlib import Path

PROJECT_ROOT = os.environ.get('PROJECT_ROOT')

if PROJECT_ROOT is None:
    raise ValueError("PROJECT_ROOT environment variable is not set")

ROOT = Path(PROJECT_ROOT);

if not ROOT.exists():
    raise ValueError(f"PROJECT_ROOT points to non-existent path: '{ROOT}'")



# Access environment variables set by direnv
CHROME_USER_DIR = os.environ.get('CHROME_USER_DIR')
CHROME_PROFILE = os.environ.get('CHROME_PROFILE')

# Validate config
if CHROME_USER_DIR is None:
    raise ValueError("CHROME_USER_DIR environment variable is not set")
if CHROME_PROFILE is None:
    raise ValueError("CHROME_PROFILE environment variable is not set")

# Ensure paths are expanded
CHROME_USER_DIR = Path(CHROME_USER_DIR).expanduser()
