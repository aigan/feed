#!/bin/env python
import argparse
import shutil
from itertools import islice

from config import ROOT


def migrate_video_files(limit=None):
    """Migrate video files from flat structure to directory structure."""
    videos_dir = ROOT / "data/youtube/videos/active"

    # Find all existing video JSON files
    video_files = []
    for shard_dir in videos_dir.glob("??"):  # Matches two-character directories
        if shard_dir.is_dir():
            video_files.extend(shard_dir.glob("*.json"))

    print(f"Found {len(video_files)} video files to migrate")

    # Process each file
    for video_file in islice(video_files, limit):
        video_id = video_file.stem
        new_dir = video_file.parent / video_id
        new_file = new_dir / "video.json"

        # Create directory if it doesn't exist
        new_dir.mkdir(exist_ok=True)

        # Only move if destination doesn't exist to prevent data loss
        if not new_file.exists():
            print(f"Moving {video_file} to {new_file}")
            shutil.move(video_file, new_file)
        else:
            print(f"Skipping {video_id} - already migrated")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Migrate video files to directory structure.')
    parser.add_argument('--limit', type=int, default=None, help='Process at most N files (default: no limit)')
    args = parser.parse_args()

    migrate_video_files(limit=args.limit)
    print("Migration complete")
