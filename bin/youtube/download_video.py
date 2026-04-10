#!/bin/env python

import argparse

from youtube import Media, iterate_videos


parser = argparse.ArgumentParser(description='Download YouTube videos.')
parser.add_argument('source_id', help='Video ID, channel ID (UC...), or playlist ID (PL...)')
args = parser.parse_args()

downloaded = 0
errors = 0

try:
    for video in iterate_videos(args.source_id):
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
