#!/bin/env python
import sqlite3
import sys

from analysis.description_filter import DescriptionFilter
from youtube import Channel, Subscription

THRESHOLD = DescriptionFilter.THRESHOLD


def channel_stats(channel_id):
    db_path = Channel.get_active_dir(channel_id) / 'text-blocks.db'
    if not db_path.exists():
        return None

    db = sqlite3.connect(str(db_path))
    videos = db.execute('SELECT COUNT(DISTINCT video_id) FROM blocks').fetchone()[0]
    total = db.execute('SELECT COUNT(*) FROM blocks').fetchone()[0]
    unique = db.execute('SELECT COUNT(DISTINCT checksum) FROM blocks').fetchone()[0]

    repeated_blocks = db.execute('''
        SELECT COUNT(*) FROM blocks WHERE checksum IN (
            SELECT checksum FROM blocks GROUP BY checksum HAVING COUNT(DISTINCT video_id) >= ?
        )
    ''', (THRESHOLD,)).fetchone()[0]

    db.close()
    return videos, total, unique, repeated_blocks


def main():
    single_channel = sys.argv[1] if len(sys.argv) > 1 else None

    if single_channel:
        subs = [type('Sub', (), {'channel_id': single_channel, 'title': single_channel})]
    else:
        subs = sorted(Subscription.get_all(), key=lambda s: s.title)

    rows = []
    for sub in subs:
        stats = channel_stats(sub.channel_id)
        if not stats:
            continue
        videos, total, unique, repeated = stats
        ratio = (repeated / total * 100) if total else 0.0
        rows.append((sub.title, videos, total, unique, repeated, ratio))

    rows.sort(key=lambda r: r[5], reverse=True)

    header = f'{"Channel":<40} {"Videos":>6}  {"Blocks":>6}  {"Unique":>6}  {"Repeated":>8}  {"Boilerplate%":>12}'
    print(header)
    print('-' * len(header))

    total_channels = len(rows)
    total_videos = 0
    total_blocks = 0
    total_repeated = 0

    for title, videos, blocks, unique, repeated, ratio in rows:
        name = title[:40]
        print(f'{name:<40} {videos:>6}  {blocks:>6}  {unique:>6}  {repeated:>8}  {ratio:>11.1f}%')
        total_videos += videos
        total_blocks += blocks
        total_repeated += repeated

    overall_ratio = (total_repeated / total_blocks * 100) if total_blocks else 0.0
    print()
    print(f'Total: {total_channels} channels, {total_videos} videos, {total_blocks} blocks, {overall_ratio:.1f}% boilerplate')


main()
