#!/bin/env python

import argparse
import json
import re

from youtube import Video, iterate_videos


def _format_line(c, indent, replies_present):
    parts = [
        f"[{c['comment_id']}]",
        c.get('author_display_name', ''),
        f"| {c.get('published_at', '')}",
        f"| likes: {c.get('like_count', 0)}",
    ]
    total = c.get('total_reply_count', 0) or 0
    if replies_present is not None and total > 0:
        parts.append(f"| replies: {replies_present}/{total}")
    return indent + ' '.join(parts)


def _print_threaded(comments_dict, include_replies):
    top = sorted(
        (c for c in comments_dict.values() if c.get('parent_id') is None),
        key=lambda c: c.get('published_at') or '',
    )
    children = {}
    for c in comments_dict.values():
        pid = c.get('parent_id')
        if pid is None:
            continue
        children.setdefault(pid, []).append(c)
    for kids in children.values():
        kids.sort(key=lambda c: c.get('published_at') or '')

    for c in top:
        replies = children.get(c['comment_id'], [])
        print(_format_line(c, '', len(replies)))
        print(c.get('text_display', ''))
        print()
        if include_replies:
            for r in replies:
                print(_format_line(r, '  ', None))
                for ln in r.get('text_display', '').split('\n'):
                    print('  ' + ln)
                print()


def _print_grep(comments_dict, pattern, include_replies):
    rx = re.compile(pattern, re.IGNORECASE)
    for c in comments_dict.values():
        if c.get('parent_id') is not None and not include_replies:
            continue
        text = c.get('text_display', '')
        if rx.search(text):
            indent = '  ' if c.get('parent_id') else ''
            print(_format_line(c, indent, None))
            for ln in text.split('\n'):
                print(indent + ln)
            print()


def _print_fetch_state(data):
    n = len(data.get('comments', {}))
    pages = data.get('pages_fetched', 0)
    if data.get('comments_disabled'):
        print(f'Comments disabled. {n} comments preserved locally.')
    elif data.get('fetch_complete'):
        print(f'Fetched {n} comments across {pages} pages — complete')
    else:
        token = data.get('next_page_token')
        print(f'Fetched {n} comments across {pages} pages — INCOMPLETE: nextPageToken={token}')

    children_count = {}
    for c in data.get('comments', {}).values():
        pid = c.get('parent_id')
        if pid is not None:
            children_count[pid] = children_count.get(pid, 0) + 1
    threads_with_gaps = 0
    missing_replies = 0
    total_replies = 0
    for c in data.get('comments', {}).values():
        if c.get('parent_id') is not None:
            continue
        total = c.get('total_reply_count', 0) or 0
        present = children_count.get(c['comment_id'], 0)
        if total > present:
            threads_with_gaps += 1
            missing_replies += (total - present)
            total_replies += total
    if threads_with_gaps:
        print(f'{threads_with_gaps} threads have replies not fetched ({missing_replies} of {total_replies} missing)')


def _print_single_thread(comments_dict, top_level_id):
    top = comments_dict.get(top_level_id)
    if not top:
        print(f'Thread {top_level_id} not in cache.')
        return
    children = sorted(
        (c for c in comments_dict.values() if c.get('parent_id') == top_level_id),
        key=lambda c: c.get('published_at') or '',
    )
    print(_format_line(top, '', len(children)))
    print(top.get('text_display', ''))
    print()
    for r in children:
        print(_format_line(r, '  ', None))
        for ln in r.get('text_display', '').split('\n'):
            print('  ' + ln)
        print()


def show_comments(video, comment_id=None, force=False, comment_limit=None, include_replies=False, grep=None):
    if comment_id:
        file = Video.get_active_comments_file(video.video_id)
        if not file.exists():
            video.mirror_comments()
        video.expand_replies(comment_id, force=force)
    else:
        video.mirror_comments(comment_limit=comment_limit, force=force)

    header = f'{video.video_id}  {video.title}'
    print(f'\n{"=" * len(header)}')
    print(header)
    print(f'{"=" * len(header)}\n')

    file = Video.get_active_comments_file(video.video_id)
    if not file.exists():
        print(f'No comments stored for {video.video_id}')
        return

    data = json.loads(file.read_text())
    _print_fetch_state(data)
    print()

    comments = data.get('comments', {})
    if comment_id:
        _print_single_thread(comments, comment_id)
    elif grep:
        _print_grep(comments, grep, include_replies)
    else:
        _print_threaded(comments, include_replies)


parser = argparse.ArgumentParser(description='Show YouTube comments.')
parser.add_argument('source_id', help='Video ID, channel ID (UC...), or playlist ID (PL...)')
parser.add_argument('comment_id', nargs='?', default=None, help='If given, deep-fetch this thread\'s replies and show only that thread.')
parser.add_argument('--force', action='store_true', help='Refetch from scratch (ignore cache and prior incomplete/expanded state)')
parser.add_argument('--limit', type=int, default=None, help='Cap comments fetched per video (default: all). Resumes where a prior incomplete run stopped unless --force is used.')
parser.add_argument('--include-replies', action='store_true', help='Include reply rows in the threaded view')
parser.add_argument('--grep', metavar='PATTERN', help='Filter comments whose text_display matches PATTERN (regex, case-insensitive)')
args = parser.parse_args()

errors = 0

try:
    for video in iterate_videos(args.source_id):
        try:
            show_comments(video,
                comment_id=args.comment_id,
                force=args.force,
                comment_limit=args.limit,
                include_replies=args.include_replies,
                grep=args.grep,
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
