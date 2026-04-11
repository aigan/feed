#!/bin/env python

import argparse
from itertools import islice

from youtube import Media, iterate_videos


parser = argparse.ArgumentParser(description='Download YouTube videos.')
parser.add_argument('source_id', help='Video ID, channel ID (UC...), or playlist ID (PL...)')
parser.add_argument('--limit', type=int, default=None, help='Process at most N videos (default: no limit)')
args = parser.parse_args()

downloaded = 0
errors = 0

try:
    for video in islice(iterate_videos(args.source_id), args.limit):
        video_id = video.video_id

        header = f'{video_id}  {video.title}'
        print(f'\n{header}')
        print(f'{"-" * len(header)}')

        try:
            path = Media.download(video_id)
            if path:
                print(f'  -> {path}')
                downloaded += 1
            else:
                errors += 1
                print(f'  -> FAILED')
        except Exception as e:
            errors += 1
            print(f'[error] {video_id}: {e}')
except KeyboardInterrupt:
    print('\nInterrupted')

total = downloaded + errors
print(f'\nDone: {downloaded} downloaded, {errors} errors ({total} total)')
