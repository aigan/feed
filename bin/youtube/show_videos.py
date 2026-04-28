#!/bin/env python

import argparse
import re
from itertools import islice

from youtube import iterate_videos


def _clean(text):
    return (text or '').replace('\t', ' ').replace('\n', ' ').strip()


def show_video(video):
    date = video.published_at.strftime('%Y-%m-%d') if video.published_at else '----------'
    channel_name = _clean(video.channel.title)
    title = _clean(video.title)
    print(f'{date}  {video.channel_id}  {channel_name}  {video.video_id}  {title}')


parser = argparse.ArgumentParser(description='List YouTube videos.')
parser.add_argument('source_id', help='Video ID, channel ID (UC...), or playlist ID (PL...)')
parser.add_argument('--limit', type=int, default=None, help='Show at most N videos')
parser.add_argument('--grep', metavar='PATTERN', help='Filter by title (regex, case-insensitive)')
args = parser.parse_args()

rx = re.compile(args.grep, re.IGNORECASE) if args.grep else None

errors = 0

try:
    for video in islice(iterate_videos(args.source_id), args.limit):
        try:
            if rx and not rx.search(video.title or ''):
                continue
            show_video(video)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors += 1
            print(f'[error] {video.video_id}: {e}')
except KeyboardInterrupt:
    print('\nInterrupted')

if errors:
    print(f'\n{errors} errors')
