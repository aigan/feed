#!/bin/env python
"""
Migrate processed transcripts to the normalized two-phase layout.

Target state (v3):
    processed/transcript.txt        # cleaned transcript, no headings inline
    processed/transcript_v1.txt     # backup of the original v1 assembled file
    processed/headings.txt          # separate heading list (regenerated fresh)
    processed/headings_v1.txt       # backup of any v1 heading list
    transcript-meta.json            # has `cleanup_prompt_version` stamped

Per video the migration handles three possible starting states:

1. **Fresh v1** — only `processed/transcript.txt` exists (old assembled format
   with `##` headings inline). Back it up to `transcript_v1.txt`, strip the
   heading lines, write the result back to `transcript.txt`.

2. **Partially migrated (v2)** — a previous run wrote `transcript_cleaned.txt`
   and `transcript_v1.txt`. A fresh formatter run may have also re-assembled
   an `transcript.txt`. Delete that stale assembled file and rename
   `transcript_cleaned.txt` → `transcript.txt`.

3. **Already v3** — `transcript.txt` exists alongside `transcript_v1.txt`
   with no `transcript_cleaned.txt`. Nothing to do.

Also run per video regardless of transcript state:

- **Unavailability marker** — `transcript-unavailable.json` is rewritten as
  `transcript-meta.json` (schema: `unavailable_reason` + `checked_at`).

Idempotent. Safe to re-run.
"""
import argparse
import json

from analysis import YTTranscriptFormatter
from config import ROOT
from util import dump_json

ACTIVE_RESULTS = {
    'marker_migrated',
    'marker_dry_run',
    'v1_to_v3_migrated',
    'v1_to_v3_dry_run',
    'v2_to_v3_migrated',
    'v2_to_v3_dry_run',
}


def strip_heading_lines(text: str) -> str:
    return '\n'.join(line for line in text.split('\n') if not line.lstrip().startswith('##'))


def iter_video_dirs(videos_dir):
    for shard_dir in videos_dir.glob('??'):
        if not shard_dir.is_dir():
            continue
        for video_dir in shard_dir.iterdir():
            if video_dir.is_dir():
                yield video_dir


def migrate_unavailable_marker(video_dir, dry_run=False):
    old_file = video_dir / 'transcript-unavailable.json'
    meta_file = video_dir / 'transcript-meta.json'
    if not old_file.exists():
        return None

    old_data = json.loads(old_file.read_text())
    new_fields = {}
    if 'reason' in old_data:
        new_fields['unavailable_reason'] = old_data['reason']
    if 'checked_at' in old_data:
        new_fields['checked_at'] = old_data['checked_at']

    if dry_run:
        print(f'[dry-run] {video_dir.name}: would merge transcript-unavailable.json into transcript-meta.json')
        return 'marker_dry_run'

    existing = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    existing.update(new_fields)
    dump_json(meta_file, existing)
    old_file.unlink()
    print(f'{video_dir.name}: migrated unavailable marker')
    return 'marker_migrated'


def stamp_meta(video_dir, updates, dry_run=False):
    meta_file = video_dir / 'transcript-meta.json'
    if dry_run:
        return
    data = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    data.update(updates)
    dump_json(meta_file, data)


def migrate_processed(video_dir, dry_run=False):
    processed = video_dir / 'processed'
    if not processed.is_dir():
        return None

    transcript_file = processed / 'transcript.txt'
    v1_backup = processed / 'transcript_v1.txt'
    cleaned_file = processed / 'transcript_cleaned.txt'
    headings_file = processed / 'headings.txt'
    headings_v1 = processed / 'headings_v1.txt'

    # State 2: partially migrated — `transcript_cleaned.txt` is the
    # canonical cleaned content. Rename it over `transcript.txt` and
    # discard any stale assembled file that the formatter may have
    # regenerated between migration runs.
    if cleaned_file.exists():
        if dry_run:
            actions = ['rename transcript_cleaned.txt → transcript.txt']
            if transcript_file.exists():
                actions.insert(0, 'remove stale assembled transcript.txt')
            print(f'[dry-run] {video_dir.name}: v2 → v3 ({", ".join(actions)})')
            return 'v2_to_v3_dry_run'
        if transcript_file.exists():
            transcript_file.unlink()
        cleaned_file.rename(transcript_file)
        print(f'{video_dir.name}: v2 → v3 (normalized transcript.txt)')
        return 'v2_to_v3_migrated'

    # State 3: already normalized.
    if transcript_file.exists() and v1_backup.exists():
        return 'already_v3'

    # State 1: fresh v1 — a single assembled transcript.txt with `##`
    # headings inline. Back it up, strip, write back.
    if transcript_file.exists():
        original = transcript_file.read_text()
        stripped = strip_heading_lines(original)
        if dry_run:
            print(
                f'[dry-run] {video_dir.name}: v1 → v3 '
                f'(backup + strip {len(original)} → {len(stripped)} bytes)'
            )
            if headings_file.exists():
                print(f'[dry-run] {video_dir.name}: would move headings.txt → headings_v1.txt')
            print(
                f'[dry-run] {video_dir.name}: would stamp cleanup_prompt_version='
                f'{YTTranscriptFormatter.CLEANUP_PROMPT_VERSION}'
            )
            return 'v1_to_v3_dry_run'
        transcript_file.rename(v1_backup)
        transcript_file.write_text(stripped)
        if headings_file.exists():
            headings_file.rename(headings_v1)
        stamp_meta(
            video_dir,
            {'cleanup_prompt_version': YTTranscriptFormatter.CLEANUP_PROMPT_VERSION},
        )
        print(
            f'{video_dir.name}: v1 → v3 '
            f'(stripped {len(stripped)} bytes, stamped cleanup v{YTTranscriptFormatter.CLEANUP_PROMPT_VERSION})'
        )
        return 'v1_to_v3_migrated'

    return 'no_transcript'


def migrate_all(limit=None, dry_run=False):
    videos_dir = ROOT / 'data/youtube/videos/active'
    stats = {}
    touched = 0
    for video_dir in iter_video_dirs(videos_dir):
        marker_result = migrate_unavailable_marker(video_dir, dry_run=dry_run)
        if marker_result is not None:
            stats[marker_result] = stats.get(marker_result, 0) + 1

        processed_result = migrate_processed(video_dir, dry_run=dry_run)
        if processed_result is not None:
            stats[processed_result] = stats.get(processed_result, 0) + 1

        if marker_result in ACTIVE_RESULTS or processed_result in ACTIVE_RESULTS:
            touched += 1
            if limit is not None and touched >= limit:
                break

    print()
    for key, count in sorted(stats.items()):
        print(f'  {key}: {count}')
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=None, help='Stop after N videos actually touched by the migration (ignores no-op visits)')
    parser.add_argument('--dry-run', action='store_true', help='Report what would change without writing')
    args = parser.parse_args()
    migrate_all(limit=args.limit, dry_run=args.dry_run)
