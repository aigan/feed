#!/bin/env python

import argparse

from youtube_transcript_api._errors import IpBlocked, RequestBlocked

from youtube import Video, Transcript, iterate_videos
from util import dump_json


def has_transcript(video_id):
    return (Video.get_active_dir(video_id) / 'transcript.json').exists()


def download_one(video, force=False):
    video_id = video.video_id

    if not force and has_transcript(video_id):
        return 'skip'

    print(f'[download] {video_id} {video.title}')

    transcript = Transcript.download(video_id)
    if transcript is None:
        print(f'[no transcript] {video_id}')
        return 'none'

    data_file = Video.get_active_dir(video_id) / 'transcript.json'
    data_file.parent.mkdir(parents=True, exist_ok=True)
    dump_json(data_file, transcript)

    lang = transcript['metadata']['language_code']
    segments = transcript['metadata']['segment_count']
    generated = 'auto' if transcript['metadata']['is_generated'] else 'manual'
    print(f'  {lang} ({generated}), {segments} segments')

    return 'ok'


def run_batch(source_id, force=False):
    downloaded = 0
    skipped = 0
    missing = 0
    errors = 0

    try:
        for video in iterate_videos(source_id):
            try:
                result = download_one(video, force=force)
                if result == 'skip':
                    skipped += 1
                elif result == 'none':
                    missing += 1
                else:
                    downloaded += 1
            except (IpBlocked, RequestBlocked):
                print('[blocked] IP blocked by YouTube, stopping batch')
                break
            except Exception as e:
                errors += 1
                print(f'[error] {video.video_id}: {type(e).__name__}')
    except KeyboardInterrupt:
        print('\nInterrupted')

    return downloaded, skipped, missing, errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Download YouTube transcripts.')
    parser.add_argument('source_id', help='Video ID, channel ID (UC...), or playlist ID (PL...)')
    parser.add_argument('--force', action='store_true', help='Re-download even if transcript exists')
    args = parser.parse_args()

    downloaded, skipped, missing, errors = run_batch(args.source_id, force=args.force)

    total = downloaded + skipped + missing + errors
    print(f'\nDone: {downloaded} downloaded, {skipped} skipped, {missing} no transcript, {errors} errors ({total} total)')
