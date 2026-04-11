#!/bin/env python

import argparse

from youtube_transcript_api._errors import IpBlocked, RequestBlocked

from analysis import YTTranscriptFormatter
from youtube import iterate_videos


def process_one(video, force=False):
    print(f'[fetch] {video.video_id} {video.title}')
    return YTTranscriptFormatter.get(video, force=force)


def run_batch(source_id, force=False, limit=None):
    processed = 0
    cached = 0
    missing = 0
    errors = 0
    work_done = 0

    try:
        for video in iterate_videos(source_id):
            if limit is not None and work_done >= limit:
                break
            try:
                result = process_one(video, force=force)
            except (IpBlocked, RequestBlocked):
                print('[blocked] IP blocked by YouTube, stopping batch')
                break
            except Exception as e:
                errors += 1
                work_done += 1
                print(f'[error] {video.video_id}: {type(e).__name__}')
                continue

            if not result.text:
                missing += 1
            elif result.did_work:
                processed += 1
            else:
                cached += 1

            if result.did_work:
                work_done += 1
    except KeyboardInterrupt:
        print('\nInterrupted')

    return processed, cached, missing, errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch YouTube transcripts (download + format).')
    parser.add_argument('source_id', help='Video ID, channel ID (UC...), or playlist ID (PL...)')
    parser.add_argument('--force', action='store_true',
                        help='Re-download and re-process even if cached output exists')
    parser.add_argument('--limit', type=int, default=None,
                        help='Stop after N videos where work was actually done (cached videos do not count)')
    args = parser.parse_args()

    processed, cached, missing, errors = run_batch(args.source_id, force=args.force, limit=args.limit)

    total = processed + cached + missing + errors
    print(f'\nDone: {processed} processed, {cached} already cached, {missing} no transcript, {errors} errors ({total} touched)')
