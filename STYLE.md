# Code Style Guide

Use this document as a checklist after implementation to ensure code quality.

## Quick Reference - Common Mistakes to Avoid

**Semicolons**: ✓ `count = 0` • ✗ `count = 0;`
**Dead code**: ✓ Delete unused code • ✗ Comment it out (`#pprint(data)`)
**Imports**: ✓ Remove unused imports • ✗ Leave `pprint` imported for future debugging
**Paths**: ✓ `config.DATA_DIR / 'videos'` • ✗ `os.path.join(data_dir, 'videos')`
**Guards**: ✓ Let it crash if it's a bug • ✗ `if data: ...` when data should always exist
**Quotes**: ✓ Single quotes `'hello'` • ✗ Double quotes `"hello"` (except when string contains `'`)

## Philosophy

Write short, readable, pragmatic code. Prefer clarity over cleverness. Fewer lines means more code visible on screen. No premature abstraction — wait for patterns to emerge before extracting helpers. Three similar lines of code is better than a premature helper function.

This is a personal data pipeline, not a library. Optimize for readability and ease of change, not reusability or extensibility.

## Naming

- ✓ `snake_case` for functions, methods, and variables
- ✓ `PascalCase` for classes
- ✓ Descriptive names — no abbreviations unless obvious (`id`, `dir`, `config` are fine)
- ✓ Boolean variables: `is_`, `has_`, `can_` prefixes
- ✓ Specific verb prefixes for methods:
  - `get_` — load from local storage, falling back to update
  - `retrieve_` — fetch from remote API
  - `update_` — retrieve and save, handle versioning
  - `find_` — search/lookup
  - `fetch_` — lighter-weight API call (subset of retrieve)

## Formatting

- ✓ 4-space indentation
- ✓ Single quotes for strings (double quotes when string contains `'`)
- ✓ No semicolons
- ✓ No trailing whitespace
- ✓ No commented-out code left behind — delete it, git has history
- ✓ Blank line between top-level definitions
- ✓ No blank lines at end of file

## Imports

Absolute imports via `PYTHONPATH=lib`. Grouped in order:

```python
from __future__ import annotations          # 1. future (if needed)

from dataclasses import dataclass, fields   # 2. stdlib
from datetime import datetime
from pathlib import Path
import json

from deepdiff import DeepDiff              # 3. third-party

from util import to_obj, dump_json         # 4. local (lib/)
from youtube.video import Video
import config
```

- ✓ One import per line for `from` imports (or grouped from same module)
- ✓ Lazy imports inside method bodies only when needed to break circular dependencies
- ✗ No wildcard imports (`from module import *`)

## Type Annotations

- ✓ Required on dataclass fields — always annotate every field
- ✓ Optional on function signatures — add them when they clarify intent
- ✓ Use `from __future__ import annotations` for forward references
- ✓ Use `Optional[T]` or `T | None` for nullable fields
- ✗ Don't add annotations purely for ceremony — they should help readability

```python
@dataclass
class Video:
    video_id: str                    # always annotated
    title: str
    published_at: datetime
    duration: Optional[str] = None

    @classmethod
    def get(cls, video_id):          # parameter types optional
        ...
```

## Data Patterns

- ✓ `@dataclass` for domain models (Video, Channel, Subscription, etc.)
- ✓ `SafeNamespace` / `to_obj()` for wrapping API responses (dot-access, missing fields return falsy `NoneObject`)
- ✓ `pathlib.Path` always — never `os.path`
- ✓ `json.loads()` / `dump_json()` for JSON I/O
- ✓ `convert_fields(cls, data)` to coerce dict values to match dataclass field types
- ✓ `to_serializable()` to convert dataclass instances to JSON-safe dicts
- ✓ `DeepDiff` for comparing old vs new data before archiving

### Classmethod factory pattern

Domain models follow a consistent `get` / `update` / `retrieve` pattern:

```python
@dataclass
class Video:
    @classmethod
    def retrieve(cls, video_id):
        """Fetch from YouTube API, return raw dict."""
        ...

    @classmethod
    def update(cls, video_id):
        """Retrieve, compare with local, archive if changed, save."""
        ...

    @classmethod
    def get(cls, video_id):
        """Load from local JSON, fall back to update() if missing."""
        ...
```

## Code Structure

- ✓ Keep functions short (prefer < 30 lines)
- ✓ Early returns to reduce nesting
- ✓ Generators for paginated API results and large collections
- ✓ Properties for computed values (`duration_seconds`, `local_uploads_count`)
- ✓ `@classmethod` for data access, instance methods for operations
- ✓ Inner classes for tightly coupled state (`Channel.SyncState`)

## Comments

- ✓ Minimal — prefer self-documenting code
- ✓ Comment "why", not "what"
- ✓ TODO comments for known issues: `# TODO: handle edge case X`
- ✗ No docstrings unless genuinely needed for complex logic
- ✗ No commented-out debug prints — delete them

## Error Handling

- ✓ Fail early with descriptive errors
- ✓ Catch specific exceptions: `except HttpError as e:` with status code checking
- ✓ Custom exceptions when semantically useful (`PlaylistInaccessibleError`)
- ✓ Let exceptions bubble up — don't catch and silence
- ✓ Use `print()` for progress/status output (this is a CLI pipeline, not a library)
- ✗ No defensive programming that hides bugs — if something should exist, don't guard against its absence

## Anti-Patterns

- ✗ Stray semicolons (`count = 0;`)
- ✗ Commented-out debug code (`#pprint(data)`)
- ✗ Deep nesting (> 3 levels) — extract functions instead
- ✗ Unused imports left behind
- ✗ Premature abstraction — don't create helpers for one-time operations
- ✗ Defensive guards for impossible states — let bugs crash visibly
- ✗ `os.path` when `pathlib` works
- ✗ Magic strings/numbers without context — use named constants or comments
- ✗ Overly broad `except Exception` — catch specific errors

## Post-Implementation Checklist

After implementing a feature, verify:

1. **Correctness**
   - [ ] Scripts run without errors
   - [ ] Data files are written to expected locations

2. **Readability**
   - [ ] Variable names are clear and descriptive
   - [ ] Functions are short and focused
   - [ ] No unnecessary comments or dead code

3. **Style**
   - [ ] No semicolons
   - [ ] No commented-out code
   - [ ] No unused imports
   - [ ] Single quotes for strings
   - [ ] Imports properly grouped

4. **Architecture**
   - [ ] Follows existing patterns (dataclass models, classmethod factories)
   - [ ] Uses `pathlib.Path` for file operations
   - [ ] Uses `SafeNamespace` / `to_obj()` for API data
   - [ ] Consistent with neighboring code
