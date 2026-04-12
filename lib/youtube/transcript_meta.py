import json
from pathlib import Path

from context import Context
from util import dump_json


class TranscriptMeta:
    """
    Metadata about a video's transcript pipeline state.

    Lives at `active_dir/transcript-meta.json` and consolidates:
    - unavailability marker (`unavailable_reason`, `checked_at`)
    - transcript source download (`transcript_downloaded_at`)
    - prompt versions and update timestamps for each formatter phase
      (`cleanup_prompt_version`, `cleanup_updated_at`,
      `headings_prompt_version`, `headings_updated_at`)

    All timestamps use `Context.get().batch_time` so every file produced in a
    single batch run shares a single coordinated UTC timestamp.
    """

    FILENAME = 'transcript-meta.json'

    def __init__(self, active_dir: Path):
        self.path = active_dir / self.FILENAME
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self):
        dump_json(self.path, self.data)

    @property
    def is_unavailable(self) -> bool:
        return bool(self.data.get('unavailable_reason'))

    def mark_unavailable(self, reason: str):
        self.update({
            'unavailable_reason': reason,
            'checked_at': Context.get().batch_time.isoformat(),
        })

    def clear_unavailable(self):
        self.data.pop('unavailable_reason', None)
        self.data.pop('checked_at', None)
        self.save()

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def update(self, updates: dict):
        """Apply multiple key updates and persist in a single write."""
        self.data.update(updates)
        self.save()

    def stamp(self, key: str):
        """Set `key` to the current batch time and persist."""
        self.set(key, Context.get().batch_time.isoformat())

    def stamp_step(self, name: str, version: int):
        """
        Record completion of a formatter phase: writes both
        `{name}_prompt_version` and `{name}_updated_at` in a single save.
        """
        self.update({
            f'{name}_prompt_version': version,
            f'{name}_updated_at': Context.get().batch_time.isoformat(),
        })
