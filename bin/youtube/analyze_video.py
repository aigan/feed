#!/bin/env python

import argparse

from youtube import Video, iterate_videos
from analysis import YTAPIVideoExtractor, YTTranscriptFormatter
from analysis.description_filter import DescriptionFilter

#video_id = "pMFH1buJOKA" # Wayward Radio Ep. #3- The Grand RPG
#video_id = "-rs7LHtODh4" # Half-Life 3 - The Rise, Fall & Rebirth
#video_id = "IGLGi5RK8V8" # Interview with the "Father of the Elder Scrolls" | Julian Jensen (aka Julian LeFay)
#video_id = "u7JFmo-vaXo" # Check Out: Chains of Freedom
#video_id = "vnOrkLQAU7E" # 13 Turns to Kill the Spawn God // CHAINS OF FREEDOM // Part 19
#video_id = "OkoHyOhHEuk" # TDS Celebrates Earth Day by Tackling Climate Change | The Daily Show
#video_id = "LPBI7WVD0zI" # Top U.S. & World Headlines — April 21, 2025
#video_id = "Dnk3uwc-2qI" # Just Happened! Insane NEW Version Tesla Bot Gen 3 Revealed! Elon Musk Shocked Unique Design!


def is_processed(video_id):
    processed_dir = Video.get_processed_dir(video_id)
    return (
        (processed_dir / 'description.txt').exists()
        and (processed_dir / 'transcript.txt').exists()
    )


def process_video(video, force=False):
    video_id = video.video_id

    if not force and is_processed(video_id):
        print(f'[skip] {video_id} {video.title}')
        return 'skip'

    header = f'{video_id}  {video.title}'
    print(f'\n{"=" * len(header)}')
    print(header)
    print(f'{"=" * len(header)}\n')

    #DescriptionFilter.get(video)
    #YTTranscriptFormatter.get(video)

    summary = YTAPIVideoExtractor.get(video)
    print('\n' + summary['text'] + '\n')

    if 'evaluation' in summary:
        ev = summary['evaluation']
        print(f"  Verdict: {ev['verdict']}  |  Coverage: {ev['coverage']}")
        if ev.get('gaps'):
            print(f"  Gaps: {', '.join(ev['gaps'][:3])}")
        if ev.get('value'):
            scores = '  '.join(f'{k}: {v}' for k, v in ev['value'].items())
            print(f'  Scores: {scores}')
        print()

    return 'ok'


parser = argparse.ArgumentParser(description='Process YouTube videos.')
parser.add_argument('source_id', help='Video ID, channel ID (UC...), or playlist ID (PL...)')
parser.add_argument('--force', action='store_true', help='Re-process even if output files exist')
args = parser.parse_args()

processed = 0
skipped = 0
errors = 0

try:
    for video in iterate_videos(args.source_id):
        try:
            result = process_video(video, force=args.force)
            if result == 'skip':
                skipped += 1
            else:
                processed += 1
        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors += 1
            print(f'[error] {video.video_id}: {e}')
except KeyboardInterrupt:
    print('\nInterrupted')

total = processed + skipped + errors
print(f'\nDone: {processed} processed, {skipped} skipped, {errors} errors ({total} total)')
