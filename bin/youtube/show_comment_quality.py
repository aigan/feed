#!/bin/env python

import argparse
import json
import re

from analysis import text_features
from analysis.comment_selector import classify, load_chapters
from youtube import Channel, Subscription, Video, iterate_videos


def _format_line(comment, result):
    parts = [
        f"[{comment['comment_id']}]",
        f"{result['quality_class']:9}",
        f"score={result['score']:>5g}",
        f"tier={result['tags']['author_tier']:<10}",
        comment.get('author_display_name', ''),
    ]
    chapter_indices = result['tags'].get('chapter_indices') or []
    if chapter_indices:
        parts.append(f'chapters={chapter_indices}')
    ents = result['tags'].get('entities') or []
    if ents:
        ent_names = ', '.join(t for _, t in ents[:5])
        parts.append(f'ents=[{ent_names}]')
    return ' '.join(parts)


def _author_summary(author_channel_id, creator_id):
    if author_channel_id is None:
        return '(no channel)'
    if author_channel_id == creator_id:
        return f'{author_channel_id}  (creator of this video)'
    sub_file = Subscription.data_dir() / f'{author_channel_id}.json'
    if sub_file.exists():
        sub = json.loads(sub_file.read_text())
        return f'{author_channel_id}  subscribed: {sub.get("title", "?")}'
    chan_file = Channel.get_active_dir(author_channel_id) / 'channel.json'
    if chan_file.exists():
        chan = json.loads(chan_file.read_text())
        subs = chan.get('subscriber_count')
        uploads = chan.get('uploads_count')
        desc = (chan.get('description') or '').strip().split('\n')[0][:120]
        return (f'{author_channel_id}  {chan.get("title", "?")} — '
                f'subs={subs} uploads={uploads}\n'
                f'    {desc}')
    return f'{author_channel_id}  (unknown channel)'


def _show_detail(video, comment_id, results, comments):
    result = results.get(comment_id)
    comment = comments.get(comment_id)
    if not comment:
        print(f'  Comment {comment_id} not in cache for {video.video_id}.')
        return
    if not result:
        print(f'  Comment {comment_id} not classified.')
        return

    text = comment.get('text_original', '')
    chapters = load_chapters(video)
    timestamps = text_features.extract_timestamps(text)
    structural = text_features.structural_features(text)

    print(f'Class:    {result["quality_class"]}')
    print(f'Score:    {result["score"]}')
    print(f'Tier:     {result["tags"]["author_tier"]}')
    print()
    print(f'Author:   {comment.get("author_display_name", "?")}')
    print(f'Channel:  {_author_summary(comment.get("author_channel_id"), video.channel_id)}')
    print(f'Posted:   {comment.get("published_at")}')
    print(f'Edited:   {comment.get("updated_at")}')
    print(f'Likes:    {comment.get("like_count", 0)}')

    parent_id = comment.get('parent_id')
    if parent_id:
        print(f'Parent:   {parent_id} (this is a reply)')
    else:
        total = comment.get('total_reply_count', 0) or 0
        inline = sum(1 for c in comments.values() if c.get('parent_id') == comment_id)
        complete = comment.get('replies_complete')
        print(f'Replies:  {inline}/{total} fetched, replies_complete={complete}')

    print()
    print('Text:')
    for ln in text.split('\n'):
        print(f'  {ln}')
    print()

    breakdown = result['tags'].get('breakdown') or []
    if breakdown:
        print('Score breakdown:')
        for b in breakdown:
            note = f"   ({b['note']})" if b.get('note') else ''
            pts = b['points']
            sign = '+' if pts >= 0 else ''
            print(f'  {b["signal"]:<22} {sign}{pts:>5g}{note}')
        print(f'  {"─" * 30}')
        total = result['score']
        sign = '+' if total >= 0 else ''
        print(f'  {"TOTAL":<22} {sign}{total:>5g}')
    print()

    print('Structural features:')
    for k, v in structural.items():
        if isinstance(v, float):
            print(f'  {k:18} {v:.3f}')
        else:
            print(f'  {k:18} {v}')
    print()

    ents = result['tags'].get('entities') or []
    if ents:
        print(f'Named entities ({len(ents)}):')
        for label, name in ents:
            print(f'  {label:12} {name}')
    else:
        print('Named entities: none')
    print()

    if timestamps:
        print('Timestamps in text → chapter:')
        for offset, raw in timestamps:
            from analysis.comment_selector import chapter_for_offset
            idx = chapter_for_offset(chapters, offset)
            if idx is None:
                print(f'  {raw} ({offset}s) → no chapter')
            else:
                print(f'  {raw} ({offset}s) → chapter {idx}: {chapters[idx][1]}')
        print()


def show_comment_quality(video, comment_id=None, include_replies=False, grep=None, force=False, limit=None, sort='score'):
    results = classify(video, force=force)
    comments_file = Video.get_active_comments_file(video.video_id)
    comments = json.loads(comments_file.read_text()).get('comments', {})

    header = f'{video.video_id}  {video.title}'
    print(f'\n{"=" * len(header)}')
    print(header)
    print(f'{"=" * len(header)}\n')

    if comment_id:
        _show_detail(video, comment_id, results, comments)
        return

    rx = re.compile(grep, re.IGNORECASE) if grep else None

    counts = {'quality': 0, 'ignorable': 0, 'anti': 0}
    for cid, result in results.items():
        counts[result['quality_class']] = counts.get(result['quality_class'], 0) + 1

    print(f"quality: {counts.get('quality', 0)}  "
          f"ignorable: {counts.get('ignorable', 0)}  "
          f"anti: {counts.get('anti', 0)}")
    print()

    if sort == 'caps':
        def _sort_key(kv):
            cid, _ = kv
            text = comments.get(cid, {}).get('text_original', '') or ''
            return -text_features.mid_sentence_caps_ratio(text)
    else:
        def _sort_key(kv):
            return (
                {'quality': 0, 'anti': 1, 'ignorable': 2}.get(kv[1]['quality_class'], 3),
                -kv[1]['score'],
            )
    items = sorted(results.items(), key=_sort_key)

    shown = 0
    for cid, result in items:
        if limit is not None and shown >= limit:
            break
        if result['quality_class'] == 'ignorable':
            continue
        comment = comments.get(cid)
        if not comment:
            continue
        is_reply = comment.get('parent_id') is not None
        # Creator and subscribed replies are always shown — they're the
        # voices you don't want hidden behind a --include-replies flag.
        tier = result['tags'].get('author_tier')
        if (is_reply and not include_replies
                and tier not in ('creator', 'subscribed')):
            continue
        text = comment.get('text_display', '')
        if rx and not rx.search(text):
            continue
        indent = '  ' if is_reply else ''
        print(indent + _format_line(comment, result))
        for ln in text.split('\n'):
            print(indent + ln)
        print()
        shown += 1


parser = argparse.ArgumentParser(description='Classify YouTube comments by interestingness.')
parser.add_argument('source_id', help='Video ID, channel ID (UC...), or playlist ID (PL...)')
parser.add_argument('comment_id', nargs='?', default=None, help='If given, show only this comment with full scoring breakdown.')
parser.add_argument('--limit', type=int, default=None, help='Show at most N comments per video')
parser.add_argument('--force', action='store_true', help='Recompute classification (ignore cached comments_classified.json)')
parser.add_argument('--include-replies', action='store_true', help='Include reply rows')
parser.add_argument('--grep', metavar='PATTERN', help='Filter comments whose text matches PATTERN (regex, case-insensitive)')
parser.add_argument('--sort', choices=['score', 'caps'], default='score', help='Sort order: score (default) or caps (mid-sentence caps ratio)')
args = parser.parse_args()

errors = 0

try:
    for video in iterate_videos(args.source_id):
        try:
            show_comment_quality(video,
                comment_id=args.comment_id,
                include_replies=args.include_replies,
                grep=args.grep,
                force=args.force,
                limit=args.limit,
                sort=args.sort,
            )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            errors += 1
            print(f'[error] {video.video_id}: {e}')
except KeyboardInterrupt:
    print('\nInterrupted')

if errors:
    print(f'\n{errors} errors')
