#!/bin/env python

import argparse
import json
from datetime import datetime, timezone

from youtube import Channel, Subscription


def _format_age(published_at):
    if not published_at:
        return '?'
    days = (datetime.now(timezone.utc) - published_at).days
    if days < 30:
        return f'{days} days'
    if days < 365:
        return f'{days // 30} months'
    return f'{days // 365} years, {(days % 365) // 30} months'


def _ensure_playlists_fetched(channel_id):
    """Idempotent: pulls only the channel's playlist metadata on first call
    (1 quota unit, no items per playlist). Empty dir is the 'fetched, none
    found' marker so subsequent runs don't re-call the API."""
    from youtube.playlist import Playlist
    pdir = Channel.get_active_dir(channel_id) / 'playlists'
    if pdir.exists():
        return
    print('Fetching playlist metadata...')
    try:
        Playlist.list_for_channel(channel_id)
    except Exception as e:
        print(f'  fetch failed: {e}')
    pdir.mkdir(parents=True, exist_ok=True)


def _show_channel(arg, fetch_playlists=True):
    if arg.startswith('@'):
        chan = Channel.get_by_handle(arg)
    else:
        chan = Channel.get(arg)
    chan_dir = Channel.get_active_dir(chan.channel_id)

    if fetch_playlists:
        _ensure_playlists_fetched(chan.channel_id)

    header = f'{chan.channel_id}  {chan.title}'
    print(f'\n{"=" * len(header)}')
    print(header)
    print(f'{"=" * len(header)}\n')

    print(f'Handle:        {chan.custom_url or "(none)"}')

    sub_file = Subscription.data_dir() / f'{chan.channel_id}.json'
    if sub_file.exists():
        sub = json.loads(sub_file.read_text())
        print(f'Subscribed:    yes (since {sub.get("first_seen", "?")})')
    else:
        print('Subscribed:    no')

    print(f'Published:     {chan.published_at}  ({_format_age(chan.published_at)})')
    print(f'Subscribers:   {chan.subscriber_count}')
    print(f'Uploads:       {chan.uploads_count}')
    print(f'Views:         {chan.view_count}')
    print()

    desc = (chan.description or '').strip()
    if desc:
        print('Description:')
        for ln in desc.split('\n'):
            print(f'  {ln}')
    else:
        print('Description:   (empty)')
    print()

    thumbs_dir = chan_dir / 'thumbnails'
    thumb_meta = thumbs_dir / 'default.json'
    if thumb_meta.exists():
        meta = json.loads(thumb_meta.read_text())
        distinct = meta.get('distinct_colors', '?')
        print(f'Profile pic:   {distinct} distinct colors '
              f'({"default-letter avatar" if distinct and distinct <= 2 else "uploaded"})')
    else:
        thumb = chan.thumbnails.get('default') if isinstance(chan.thumbnails, dict) else None
        if thumb and thumb.get('url'):
            print(f'Profile pic:   {thumb["url"]} (not yet analyzed)')
        else:
            print('Profile pic:   (none)')
    print()

    pdata = chan.playlists_data or {}
    if pdata:
        print('System playlists:')
        for name, value in pdata.items():
            print(f'  {name:14} {value or "(empty)"}')
        print()

    pl_dir = chan_dir / 'playlists'
    if pl_dir.is_dir():
        pl_files = sorted(pl_dir.glob('*.json'))
        print(f'Cached user playlists: {len(pl_files)}')
        for pf in pl_files[:10]:
            try:
                pl = json.loads(pf.read_text())
                title = pl.get('title') or pl.get('snippet', {}).get('title', '?')
                count = pl.get('item_count') or pl.get('contentDetails', {}).get('itemCount', '?')
                print(f'  {pf.stem}  {title}  ({count} items)')
            except Exception as e:
                print(f'  {pf.stem}  [parse error: {e}]')
        if len(pl_files) > 10:
            print(f'  ... and {len(pl_files) - 10} more')
        print()
    else:
        print('Cached user playlists: not fetched yet')
        print()

    topics = chan.topic_details or {}
    if topics:
        cats = topics.get('topicCategories') or []
        if cats:
            print('Topic categories:')
            for cat in cats:
                print(f'  {cat}')
            print()

    uploads_dir = chan_dir / 'uploads'
    if uploads_dir.is_dir():
        years = sorted(uploads_dir.glob('*.json'), reverse=True)
        if years:
            print(f'Cached upload years: {len(years)} ({", ".join(y.stem for y in years[:5])}{"..." if len(years) > 5 else ""})')
            print()

    print(f'First seen:    {chan.first_seen}')
    print(f'Last updated:  {chan.last_updated}')


parser = argparse.ArgumentParser(description='Show details of a YouTube channel.')
parser.add_argument('channel', help='Channel ID (UC...) or handle (@username)')
parser.add_argument('--no-fetch', action='store_true', help='Skip fetching playlists if not already cached')
args = parser.parse_args()

try:
    _show_channel(args.channel, fetch_playlists=not args.no_fetch)
except KeyboardInterrupt:
    print('\nInterrupted')
