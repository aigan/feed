from __future__ import annotations

import os
import socket
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import rate_limits

import config

CROSS_HOST_STALE_SECONDS = 86400
LOCK_POLL_SECONDS = 1.0
ACQUIRE_JITTER_SECONDS = 0.05
CLEANUP_INTERVAL_SECONDS = 60
DB_FILE_MODE = 0o664

OUTCOME_OK = 'ok'
OUTCOME_BLOCKED = 'blocked'
OUTCOME_ABANDONED = 'abandoned'
OUTCOME_ERROR_PREFIX = 'error:'

CREATE_TABLE_SQL = (
    'CREATE TABLE IF NOT EXISTS request_log ('
    'id INTEGER PRIMARY KEY AUTOINCREMENT, '
    'bucket TEXT NOT NULL, '
    'cost INTEGER NOT NULL DEFAULT 1, '
    'requested_at REAL NOT NULL, '
    'released_at REAL, '
    'outcome TEXT, '
    'pid INTEGER NOT NULL, '
    'host TEXT NOT NULL)'
)
CREATE_INDEX_SQL = (
    'CREATE INDEX IF NOT EXISTS idx_bucket_requested_at '
    'ON request_log(bucket, requested_at)'
)


class UnknownBucket(Exception):
    pass


@dataclass
class Ticket:
    limiter: RateLimiter
    id: int
    bucket: str
    cost: int
    _released: bool = field(default=False, repr=False)

    def ok(self):
        self._record(OUTCOME_OK)

    def blocked(self):
        self._record(OUTCOME_BLOCKED)

    def error(self, exc=None):
        suffix = type(exc).__name__ if exc is not None else ''
        self._record(OUTCOME_ERROR_PREFIX + suffix)

    def _record(self, outcome):
        if self._released:
            return
        self._released = True
        self.limiter._release(self.id, outcome)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._released:
            return False
        if exc_type is None:
            self.ok()
        else:
            self.error(exc)
        return False


class RateLimiter:
    _instance: Optional[RateLimiter] = None

    def __init__(self):
        self.db_path = config.DATA_DIR / 'rate_limits.sqlite'
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.host = socket.gethostname()
        self._last_cleanup = 0.0
        self._local = threading.local()
        self._init_schema()
        self._fix_file_modes()

    @classmethod
    def get(cls) -> RateLimiter:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = None

    def acquire(self, bucket, cost=1) -> Ticket:
        return self._acquire(bucket, cost, blocking=True)

    def try_acquire(self, bucket, cost=1) -> Optional[Ticket]:
        return self._acquire(bucket, cost, blocking=False)

    def _acquire(self, bucket, cost, blocking):
        spec = rate_limits.BUCKETS.get(bucket)
        if spec is None:
            raise UnknownBucket(bucket)

        while True:
            result = self._check_and_insert(bucket, cost, spec)
            if isinstance(result, Ticket):
                return result
            if not blocking:
                return None
            wait_until = result
            delay = max(0.0, wait_until - time.time()) + ACQUIRE_JITTER_SECONDS
            time.sleep(delay)

    @property
    def _conn(self):
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            self._local.conn = conn
        return conn

    def _fix_file_modes(self):
        for suffix in ('', '-wal', '-shm'):
            path = self.db_path.with_name(self.db_path.name + suffix)
            try:
                current = path.stat().st_mode & 0o777
            except FileNotFoundError:
                continue
            if current != DB_FILE_MODE:
                try:
                    path.chmod(DB_FILE_MODE)
                except PermissionError:
                    pass

    def _init_schema(self):
        self._conn.execute(CREATE_TABLE_SQL)
        self._conn.execute(CREATE_INDEX_SQL)

    def _check_and_insert(self, bucket, cost, spec):
        conn = self._conn
        conn.execute('BEGIN IMMEDIATE')
        try:
            now = time.time()

            lock_wait = self._reclaim_or_wait_for_lock(conn, bucket, now)
            if lock_wait is not None:
                conn.execute('ROLLBACK')
                return lock_wait

            if now - self._last_cleanup > CLEANUP_INTERVAL_SECONDS:
                max_window = max(w for w, _ in spec['windows'])
                conn.execute(
                    'DELETE FROM request_log WHERE requested_at < ? AND outcome IS NOT NULL',
                    (now - max_window * 2,),
                )
                self._last_cleanup = now

            block_until = self._earliest_free(conn, bucket, cost, spec, now)
            if block_until is not None:
                conn.execute('ROLLBACK')
                return block_until

            cursor = conn.execute(
                'INSERT INTO request_log '
                '(bucket, cost, requested_at, pid, host) '
                'VALUES (?, ?, ?, ?, ?)',
                (bucket, cost, now, os.getpid(), self.host),
            )
            row_id = cursor.lastrowid
            conn.execute('COMMIT')
            return Ticket(limiter=self, id=row_id, bucket=bucket, cost=cost)
        except Exception:
            conn.execute('ROLLBACK')
            raise

    def _reclaim_or_wait_for_lock(self, conn, bucket, now):
        """Ensure at most one in-flight row per bucket.

        Returns None if the bucket is free to acquire, or a timestamp to
        wait until if another caller currently holds it.
        """
        row = conn.execute(
            'SELECT id, pid, host, requested_at FROM request_log '
            'WHERE bucket = ? AND outcome IS NULL '
            'ORDER BY requested_at ASC LIMIT 1',
            (bucket,),
        ).fetchone()
        if row is None:
            return None

        held_id, held_pid, held_host, held_at = row

        if held_host == self.host:
            if _pid_alive(held_pid):
                return now + LOCK_POLL_SECONDS
        elif now - held_at < CROSS_HOST_STALE_SECONDS:
            return now + LOCK_POLL_SECONDS

        conn.execute(
            'UPDATE request_log SET outcome=?, released_at=? WHERE id=?',
            (OUTCOME_ABANDONED, now, held_id),
        )
        return None

    def _earliest_free(self, conn, bucket, cost, spec, now):
        tz_name = spec.get('reset_timezone')
        wait_until = None

        for window_sec, limit in spec['windows']:
            if tz_name:
                window_start = _absolute_window_start(now, tz_name)
            else:
                window_start = now - window_sec

            row = conn.execute(
                'SELECT COALESCE(SUM(cost), 0) FROM request_log '
                'WHERE bucket = ? AND requested_at >= ? '
                "AND COALESCE(outcome, '') != ?",
                (bucket, window_start, OUTCOME_ABANDONED),
            ).fetchone()
            current = row[0]

            if current + cost <= limit:
                continue

            if tz_name:
                next_free = _next_absolute_reset(now, tz_name)
            else:
                row2 = conn.execute(
                    'SELECT MIN(requested_at) FROM request_log '
                    'WHERE bucket = ? AND requested_at >= ? '
                    "AND COALESCE(outcome, '') != ?",
                    (bucket, window_start, OUTCOME_ABANDONED),
                ).fetchone()
                oldest = row2[0] if row2[0] is not None else now
                next_free = oldest + window_sec

            if wait_until is None or next_free > wait_until:
                wait_until = next_free

        return wait_until

    def _release(self, ticket_id, outcome):
        self._conn.execute(
            'UPDATE request_log SET released_at = ?, outcome = ? WHERE id = ?',
            (time.time(), outcome, ticket_id),
        )


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _absolute_window_start(now, tz_name):
    tz = ZoneInfo(tz_name)
    now_local = datetime.fromtimestamp(now, tz=tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.timestamp()


def _next_absolute_reset(now, tz_name):
    tz = ZoneInfo(tz_name)
    now_local = datetime.fromtimestamp(now, tz=tz)
    next_local = (now_local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return next_local.timestamp()
