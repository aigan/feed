#!/bin/env python

import sqlite3
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from rate_limits import BUCKETS

import config

OUTCOME_ABANDONED = 'abandoned'


def _format_duration(secs):
    secs = int(max(secs, 0))
    if secs < 60:
        return f'{secs}s'
    if secs < 3600:
        return f'{secs // 60}m {secs % 60}s'
    if secs < 86400:
        return f'{secs // 3600}h {(secs % 3600) // 60}m'
    return f'{secs // 86400}d {(secs % 86400) // 3600}h'


def _format_window(secs):
    if secs == 60:
        return '1m'
    if secs == 3600:
        return '1h'
    if secs == 86400:
        return '1d'
    return f'{secs}s'


def _window_start(now, window_sec, tz_name):
    if tz_name:
        tz = ZoneInfo(tz_name)
        now_local = datetime.fromtimestamp(now, tz=tz)
        return now_local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return now - window_sec


def _next_calendar_reset(now, tz_name):
    tz = ZoneInfo(tz_name)
    now_local = datetime.fromtimestamp(now, tz=tz)
    next_local = (now_local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return next_local.timestamp()


def _print_bucket(conn, bucket_name, spec, now):
    tz_name = spec.get('reset_timezone')
    kind = f'calendar, midnight {tz_name}' if tz_name else 'rolling'
    print(f'\n{bucket_name}  ({kind})')
    print(f'  {"window":<7} {"used":>7} {"limit":>7} {"pct":>6}   status')
    for window_sec, limit in spec['windows']:
        ws = _window_start(now, window_sec, tz_name)
        row = conn.execute(
            'SELECT COALESCE(SUM(cost), 0) AS used, MIN(requested_at) AS oldest '
            'FROM request_log WHERE bucket = ? AND requested_at >= ? '
            "AND COALESCE(outcome, '') != ?",
            (bucket_name, ws, OUTCOME_ABANDONED),
        ).fetchone()
        used, oldest = row[0], row[1]
        pct = (used / limit * 100) if limit else 0

        if tz_name:
            status = f'resets in {_format_duration(_next_calendar_reset(now, tz_name) - now)}'
        elif used >= limit and oldest is not None:
            status = f'AT CAP — frees in {_format_duration(oldest + window_sec - now)}'
        else:
            status = 'ok'
        print(f'  {_format_window(window_sec):<7} {used:>7} {limit:>7} {pct:>5.1f}%   {status}')


def _print_outcomes(conn, now):
    print('\nOutcomes (last 24h)')
    print(f'  {"bucket":<22} {"ok":>6} {"blocked":>8} {"error":>6} {"abandon":>8} {"in_flight":>10}')
    cutoff = now - 86400
    rows = conn.execute(
        'SELECT bucket, '
        "  SUM(CASE WHEN outcome = 'ok' THEN 1 ELSE 0 END) AS ok, "
        "  SUM(CASE WHEN outcome = 'blocked' THEN 1 ELSE 0 END) AS blocked, "
        "  SUM(CASE WHEN outcome LIKE 'error:%' THEN 1 ELSE 0 END) AS errors, "
        "  SUM(CASE WHEN outcome = 'abandoned' THEN 1 ELSE 0 END) AS abandoned, "
        '  SUM(CASE WHEN outcome IS NULL THEN 1 ELSE 0 END) AS in_flight '
        'FROM request_log WHERE requested_at >= ? GROUP BY bucket ORDER BY bucket',
        (cutoff,),
    ).fetchall()
    for r in rows:
        print(f'  {r[0]:<22} {r[1]:>6} {r[2]:>8} {r[3]:>6} {r[4]:>8} {r[5]:>10}')


def _print_recent(conn):
    print('\nMost recent (last 5)')
    rows = conn.execute(
        'SELECT bucket, cost, outcome, requested_at FROM request_log '
        'ORDER BY requested_at DESC LIMIT 5'
    ).fetchall()
    for r in rows:
        ts = datetime.fromtimestamp(r[3]).strftime('%Y-%m-%d %H:%M:%S')
        outcome = r[2] or 'in_flight'
        print(f'  {ts}  {r[0]:<22} cost={r[1]}  {outcome}')


def main():
    db_path = config.DATA_DIR / 'rate_limits.sqlite'
    if not db_path.exists():
        print(f'No rate-limit database at {db_path}', file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    now = datetime.now().timestamp()

    for bucket_name, spec in BUCKETS.items():
        _print_bucket(conn, bucket_name, spec, now)

    _print_outcomes(conn, now)
    _print_recent(conn)


if __name__ == '__main__':
    main()
