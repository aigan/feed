#!/bin/env python
import json
import sqlite3
import sys

from analysis.description_filter import DescriptionFilter
from youtube import Channel, Subscription, Video

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

    uploads_dir = Channel.get_active_dir(channel_id) / "uploads"
    unique_lengths = []
    if uploads_dir.exists():
        for path in sorted(uploads_dir.glob('*.json')):
            data = json.loads(path.read_text())
            for video_id, _ in data:
                desc_file = Video.get_processed_dir(video_id) / "description.json"
                if desc_file.exists():
                    desc_data = json.loads(desc_file.read_text())
                    if "unique_length" in desc_data:
                        unique_lengths.append(desc_data["unique_length"])

    processed = len(unique_lengths)
    avg_ulen = sum(unique_lengths) / processed if processed else 0.0
    return videos, total, unique, repeated_blocks, processed, avg_ulen


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
        videos, total, unique, repeated, processed, avg_ulen = stats
        ratio = (repeated / total * 100) if total else 0.0
        rows.append((sub.title, videos, total, unique, repeated, ratio, processed, avg_ulen))

    rows.sort(key=lambda r: r[5], reverse=True)

    header = f'{"Channel":<40} {"Videos":>6}  {"Blocks":>6}  {"Unique":>6}  {"Repeated":>8}  {"Boilerplate%":>12}  {"Processed":>9}  {"Avg ULen":>8}'
    print(header)
    print('-' * len(header))

    total_channels = len(rows)
    total_videos = 0
    total_blocks = 0
    total_repeated = 0
    total_processed = 0
    all_unique_lengths_sum = 0.0

    for title, videos, blocks, unique, repeated, ratio, processed, avg_ulen in rows:
        name = title[:40]
        print(f'{name:<40} {videos:>6}  {blocks:>6}  {unique:>6}  {repeated:>8}  {ratio:>11.1f}%  {processed:>9}  {avg_ulen:>8.0f}')
        total_videos += videos
        total_blocks += blocks
        total_repeated += repeated
        total_processed += processed
        all_unique_lengths_sum += avg_ulen * processed

    overall_ratio = (total_repeated / total_blocks * 100) if total_blocks else 0.0
    overall_avg_ulen = all_unique_lengths_sum / total_processed if total_processed else 0.0
    print()
    print(f'Total: {total_channels} channels, {total_videos} videos, {total_blocks} blocks, {overall_ratio:.1f}% boilerplate, {total_processed} processed, avg unique_length {overall_avg_ulen:.0f}')


main()
