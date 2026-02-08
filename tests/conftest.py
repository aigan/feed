import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch

BATCH_TIME = datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def ctx(tmp_path):
    """Patch DATA_DIR to tmp_path, set deterministic Context.batch_time."""
    from context import Context

    Context.reset()
    instance = Context.__new__(Context)
    instance.batch_time = BATCH_TIME
    Context._instance = instance

    with patch("config.DATA_DIR", tmp_path):
        yield tmp_path

    Context.reset()


@pytest.fixture
def write_json(ctx):
    """Write a JSON file relative to the tmp DATA_DIR."""
    def _write(rel_path, data):
        path = ctx / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        return path
    return _write


@pytest.fixture
def read_json(ctx):
    """Read a JSON file relative to the tmp DATA_DIR."""
    def _read(rel_path):
        path = ctx / rel_path
        return json.loads(path.read_text())
    return _read


@pytest.fixture
def write_raw(ctx):
    """Write raw text to a file relative to the tmp DATA_DIR."""
    def _write(rel_path, text):
        path = ctx / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path
    return _write
