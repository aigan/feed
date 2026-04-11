#!/bin/env python
import argparse
import json
from itertools import islice

from analysis import DescriptionFilter
from context import Context
from util import dump_json
from youtube import Channel, Subscription, Video

batch_time = Context.get().batch_time


def process_channel(channel_id, limit=None):
    DescriptionFilter.index_channel(channel_id)

    uploads_dir = Channel.get_active_dir(channel_id) / "uploads"
    if not uploads_dir.exists():
        print("  No uploads directory")
        return

    video_ids = []
    for path in sorted(uploads_dir.glob('*.json')):
        data = json.loads(path.read_text())
        for video_id, _published_at in data:
            video_ids.append(video_id)

    print(f"  Filtering {len(video_ids)} videos")
    for i, video_id in enumerate(islice(video_ids, limit)):
        try:
            video = Video.get(video_id)
            description = DescriptionFilter.strip(video.description, video, channel_id)

            processed_dir = Video.get_processed_dir(video_id)
            processed_dir.mkdir(parents=True, exist_ok=True)
            (processed_dir / "description.txt").write_text(description + '\n')

            dump_json(processed_dir / "description.json", {
                "db_version": DescriptionFilter.DB_VERSION,
                "last_updated": video.last_updated.isoformat(),
                "unique_length": DescriptionFilter.unique_length(video.description, channel_id),
            })
        except Exception as e:
            print(f"  Error processing {video_id}: {e}")
        if (i + 1) % 1000 == 0:
            print(f"  Progress: {i + 1}/{len(video_ids)}")

    print("  Done")


parser = argparse.ArgumentParser(description='Filter video descriptions via block index.')
parser.add_argument('channel_id', nargs='?', help='Channel ID (optional; default: all subscriptions)')
parser.add_argument('--limit', type=int, default=None, help='Process at most N items (default: no limit)')
args = parser.parse_args()

if args.channel_id:
    print(f"Filtering descriptions for channel {args.channel_id}")
    process_channel(args.channel_id, limit=args.limit)
else:
    for sub in islice(Subscription.get_all(), args.limit):
        print(f"\n{sub.title} ({sub.channel_id})")
        process_channel(sub.channel_id)

print("\nDone")
