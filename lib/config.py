import os
from pathlib import Path

PROJECT_ROOT = os.environ.get('PROJECT_ROOT')

if PROJECT_ROOT is None:
    raise ValueError("PROJECT_ROOT environment variable is not set")

ROOT = Path(PROJECT_ROOT)

if not ROOT.exists():
    raise ValueError(f"PROJECT_ROOT points to non-existent path: '{ROOT}'")

DATA_DIR = Path(os.environ.get('DATA_DIR', str(ROOT / "data")))
MEDIA_DIR = Path(os.environ.get('MEDIA_DIR', '/srv/youtube'))

# Chrome config — only needed for bin/web/ scripts
CHROME_USER_DIR = os.environ.get('CHROME_USER_DIR')
CHROME_PROFILE = os.environ.get('CHROME_PROFILE')
if CHROME_USER_DIR:
    CHROME_USER_DIR = Path(CHROME_USER_DIR).expanduser()


# LLM profiles referenced by name from Processor.ask_llm(profile=...).
# Each dict is passed as **kwargs to ChatOpenAI, so new params (temperature,
# max_tokens, verbosity, ...) can be added per-profile without touching call sites.
# Rationale for the model/effort picks: var/model_comparison/ANALYSIS.md
LLM_PROFILES = {
    'cleanup':  {'model': 'gpt-5.4-mini', 'reasoning_effort': 'low'},
    'headings': {'model': 'gpt-5.4-mini', 'reasoning_effort': 'medium'},
    'label':    {'model': 'gpt-5.4-nano', 'reasoning_effort': 'low'},
    'extract':  {'model': 'gpt-5.4-mini', 'reasoning_effort': 'low'},
    'judge':    {'model': 'gpt-5.4-mini', 'reasoning_effort': 'medium'},
}
