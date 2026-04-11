from __future__ import annotations

import os
import socket
import sqlite3
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def tiny_buckets(monkeypatch):
    """Override BUCKETS with small, deterministic limits for tests."""
    import rate_limits

    buckets = {
        'test.unit': {
            'windows': [(60, 3)],
            'reset_timezone': None,
        },
        'test.cost': {
            'windows': [(86400, 1000)],
            'reset_timezone': None,
        },
        'test.multi': {
            'windows': [(1, 1), (60, 10)],
            'reset_timezone': None,
        },
        'test.absolute': {
            'windows': [(86400, 5)],
            'reset_timezone': 'America/Los_Angeles',
        },
        'test.stale': {
            'windows': [(3600, 3)],
            'reset_timezone': None,
        },
    }
    monkeypatch.setattr(rate_limits, 'BUCKETS', buckets)
    yield buckets


@pytest.fixture
def limiter(tmp_path, monkeypatch, tiny_buckets):
    """Fresh RateLimiter backed by a tmp SQLite DB."""
    import config

    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)

    from rate_limiter import RateLimiter
    RateLimiter.reset()
    instance = RateLimiter.get()
    yield instance
    RateLimiter.reset()


@pytest.fixture
def fake_clock(monkeypatch):
    """Replace time.time and time.sleep with a deterministic clock."""
    fake = [1_700_000_000.0]

    def now():
        return fake[0]

    def sleep(seconds):
        fake[0] += seconds

    import rate_limiter
    monkeypatch.setattr(rate_limiter.time, 'time', now)
    monkeypatch.setattr(rate_limiter.time, 'sleep', sleep)
    yield fake


def _rows(limiter, bucket=None):
    conn = sqlite3.connect(str(limiter.db_path))
    try:
        if bucket:
            return conn.execute(
                'SELECT id, bucket, cost, outcome FROM request_log WHERE bucket = ?',
                (bucket,),
            ).fetchall()
        return conn.execute(
            'SELECT id, bucket, cost, outcome FROM request_log'
        ).fetchall()
    finally:
        conn.close()


class TestAcquireRoundtrip:
    def test_acquire_returns_ticket(self, limiter):
        ticket = limiter.acquire('test.unit')
        assert ticket.id > 0
        assert ticket.bucket == 'test.unit'
        assert ticket.cost == 1
        ticket.ok()

    def test_row_written_on_acquire(self, limiter):
        ticket = limiter.acquire('test.unit')
        rows = _rows(limiter)
        assert len(rows) == 1
        assert rows[0][1] == 'test.unit'
        assert rows[0][3] is None
        ticket.ok()

    def test_context_manager_marks_ok(self, limiter):
        with limiter.acquire('test.unit'):
            pass
        rows = _rows(limiter)
        assert rows[0][3] == 'ok'

    def test_context_manager_marks_error(self, limiter):
        with pytest.raises(ValueError):
            with limiter.acquire('test.unit'):
                raise ValueError('boom')
        rows = _rows(limiter)
        assert rows[0][3] == 'error:ValueError'

    def test_explicit_blocked_not_overwritten_by_exit(self, limiter):
        with pytest.raises(RuntimeError):
            with limiter.acquire('test.unit') as ticket:
                ticket.blocked()
                raise RuntimeError('re-raised after blocked marker')
        rows = _rows(limiter)
        assert rows[0][3] == 'blocked'

    def test_unknown_bucket_raises(self, limiter):
        from rate_limiter import UnknownBucket
        with pytest.raises(UnknownBucket):
            limiter.acquire('youtube.nonexistent')


class TestWindowEnforcement:
    def test_try_acquire_over_budget_returns_none(self, limiter):
        for _ in range(3):
            limiter.acquire('test.unit').ok()
        assert limiter.try_acquire('test.unit') is None

    def test_try_acquire_under_budget_succeeds(self, limiter):
        for _ in range(2):
            limiter.acquire('test.unit').ok()
        ticket = limiter.try_acquire('test.unit')
        assert ticket is not None
        ticket.ok()

    def test_acquire_blocks_until_window_slides(self, limiter, fake_clock):
        for _ in range(3):
            limiter.acquire('test.unit').ok()
            fake_clock[0] += 0.001

        start = fake_clock[0]
        ticket = limiter.acquire('test.unit')
        elapsed = fake_clock[0] - start
        assert elapsed >= 60
        ticket.ok()

    def test_multi_window_strictest_wins(self, limiter, fake_clock):
        limiter.acquire('test.multi').ok()
        assert limiter.try_acquire('test.multi') is None

        fake_clock[0] += 1.1
        ticket = limiter.try_acquire('test.multi')
        assert ticket is not None
        ticket.ok()


class TestCostWeighted:
    def test_cost_sums(self, limiter):
        for _ in range(3):
            limiter.acquire('test.cost', cost=100).ok()
        conn = sqlite3.connect(str(limiter.db_path))
        total = conn.execute(
            "SELECT SUM(cost) FROM request_log WHERE bucket = 'test.cost'"
        ).fetchone()[0]
        conn.close()
        assert total == 300

    def test_cost_limit_enforced(self, limiter):
        for _ in range(10):
            limiter.acquire('test.cost', cost=100).ok()
        assert limiter.try_acquire('test.cost', cost=100) is None

    def test_partial_cost_fits(self, limiter):
        limiter.acquire('test.cost', cost=950).ok()
        assert limiter.try_acquire('test.cost', cost=100) is None
        ticket = limiter.try_acquire('test.cost', cost=50)
        assert ticket is not None
        ticket.ok()


class TestLockSerialization:
    def _insert_held(self, limiter, bucket, pid):
        conn = sqlite3.connect(str(limiter.db_path))
        conn.execute(
            'INSERT INTO request_log (bucket, cost, requested_at, pid, host) '
            'VALUES (?, ?, ?, ?, ?)',
            (bucket, 1, time.time(), pid, socket.gethostname()),
        )
        conn.commit()
        conn.close()

    def test_try_acquire_blocks_on_live_holder(self, limiter):
        self._insert_held(limiter, 'test.unit', os.getpid())
        assert limiter.try_acquire('test.unit') is None

    def test_dead_holder_is_reclaimed(self, limiter, monkeypatch):
        import rate_limiter
        monkeypatch.setattr(rate_limiter, '_pid_alive', lambda pid: False)

        self._insert_held(limiter, 'test.unit', 999_999)

        ticket = limiter.acquire('test.unit')
        ticket.ok()

        conn = sqlite3.connect(str(limiter.db_path))
        abandoned = conn.execute(
            "SELECT count(*) FROM request_log WHERE outcome = 'abandoned'"
        ).fetchone()[0]
        conn.close()
        assert abandoned == 1

    def test_cross_host_old_row_reclaimed(self, limiter, monkeypatch):
        conn = sqlite3.connect(str(limiter.db_path))
        conn.execute(
            'INSERT INTO request_log (bucket, cost, requested_at, pid, host) '
            'VALUES (?, ?, ?, ?, ?)',
            ('test.unit', 1, time.time() - 200_000, 1, 'other-host'),
        )
        conn.commit()
        conn.close()

        ticket = limiter.acquire('test.unit')
        ticket.ok()


class TestAbsoluteResetWindow:
    def test_window_resets_at_midnight_pacific(self, limiter, monkeypatch):
        pacific = ZoneInfo('America/Los_Angeles')
        before = datetime(2026, 4, 11, 23, 59, 0, tzinfo=pacific).timestamp()
        after = datetime(2026, 4, 12, 0, 1, 0, tzinfo=pacific).timestamp()
        fake = [before]

        import rate_limiter
        monkeypatch.setattr(rate_limiter.time, 'time', lambda: fake[0])

        for _ in range(5):
            limiter.acquire('test.absolute').ok()
        assert limiter.try_acquire('test.absolute') is None

        fake[0] = after
        ticket = limiter.try_acquire('test.absolute')
        assert ticket is not None
        ticket.ok()


class TestConcurrency:
    def test_threads_serialize(self, limiter):
        acquired_order = []
        lock = threading.Lock()

        def worker(i):
            with limiter.acquire('test.unit'):
                with lock:
                    acquired_order.append(i)
                time.sleep(0.01)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(acquired_order) == [0, 1, 2]
