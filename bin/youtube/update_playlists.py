#!/bin/env python
from youtube import get_youtube_client
from pprint import pprint
from datetime import datetime, timezone
from config import ROOT
from util import to_obj, from_obj, dump_json
from pathlib import Path
import json
from deepdiff import DeepDiff
from difflib import SequenceMatcher

batch_time = datetime.now(timezone.utc)
output_dir = ROOT / "data/youtube/playlists/active"
archive_dir = ROOT / "data/youtube/playlists/archive"

def retrieve_playlist():
    youtube = get_youtube_client()
    request = youtube.playlists().list(
        #part="id",
        part="id,contentDetails,status,snippet",
        #part="snippet",
        mine=True,
        #id="PLbvfm0ge12qlqWpmgraY0b0ntj5J9k_h6",
        maxResults=50
    )
    playlist_ids = []
    
    while request:
        response = request.execute()
        #pprint(response)
        #break
        
        for item in to_obj(response['items']):
            id = item.id
            playlist_ids.append(id)
            output_file = output_dir / f"{id}.json"
        
            new_data = {
                'playlist_id': id,
                'title': item.snippet.title,
                'etag': item.etag,
                'channel_id': item.snippet.channelId,
                'published_at': datetime.fromisoformat(item.snippet.publishedAt).isoformat(),
                'item_count': item.contentDetails.itemCount,
                'privacy_status': item.status.privacyStatus,
                'description': item.snippet.description,
                'thumbnails': from_obj(item.snippet.thumbnails),
            }

            new_data_stamps = {
                'last_updated': batch_time.isoformat(),
                'items_last_updated': batch_time.isoformat(),
            }

            if output_file.exists():
                data = json.loads(output_file.read_text())
                (new_items_etag, video_ids) = get_playlist_items(id, data.get('items_etag'))
                # etag depends on parts requested
                if data.get('etag') == item.etag and data.get('items_etag') == new_items_etag:
                    continue
                print(f"Update {id}")

                new_data['items_etag'] = new_items_etag
                new_data['items'] = video_ids or data['items']
                #pprint(new_data)

                exclude_paths = [
                    "root['first_seen']",
                    "root['last_updated']",
                    "root['items_last_updated']"
                ]
                diff = DeepDiff(
                    data, new_data,
                    ignore_order=False,
                    exclude_paths=exclude_paths,
                )
                if diff:
                    archive_playlist(data.copy())
            else:
                print(f"Created {id}");
                (new_items_etag, video_ids) = get_playlist_items(id)
                new_data['items_etag'] = new_items_etag
                new_data['items'] = video_ids
                data = {'first_seen': batch_time.isoformat()}

            data.update(new_data)
            data.update(new_data_stamps)
            dump_json(output_file, data)
            
        request = youtube.playlists().list_next(request, response)
        #request = False

    return playlist_ids;

def archive_playlist(data):
    year = batch_time.year
    week_number = batch_time.isocalendar()[1]
    slot_dir = archive_dir / str(year) / f"week-{week_number:02}"
    id = data['playlist_id']
    archive_file = slot_dir / f"{id}.json"
    if archive_file.exists():
        old_data = json.loads(archive_file.read_text())
        data['items'] = merge_ordered(old_data['items'], data['items'])
        data.pop('items_etag')
    dump_json(archive_file,data)

def archive_removed_playlist(id):
    output_file = output_dir / f"{id}.json"
    data = json.loads(output_file.read_text())
    data['removed_at'] = batch_time.isoformat()
    archive_playlist(data)
    output_file.unlink()
    print(f"Archived {id}")

def merge_ordered(old, new):
    """Merge new into old, preserving order as much as possible."""
    matcher = SequenceMatcher(None, old, new)
    result = []
    i_old, i_new = 0, 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            result.extend(old[i1:i2])
            i_old, i_new = i2, j2
        elif tag == 'insert':
            result.extend(new[j1:j2])
            i_new = j2
        elif tag == 'replace':
            result.extend(old[i1:i2])
            result.extend(new[j1:j2])
            i_old, i_new = i2, j2
        elif tag == 'delete':
            result.extend(old[i1:i2])
            i_old = i2

    # Append any remaining elements
    result.extend(old[i_old:])
    result.extend(new[i_new:])

    return list(dict.fromkeys(result)) # Remove duplicates

def get_playlist_items(id, etag=None):
    youtube = get_youtube_client()
    #pprint(data)
    request = youtube.playlistItems().list(
        playlistId=id,
        part="contentDetails",
        maxResults=50,
    )

    first_response = request.execute()
    new_etag = first_response['etag']

    if etag and etag == new_etag:
        print(f"List {id} unchanged")
        return (new_etag, None)

    video_ids = []
    for item in first_response['items']:
        video_ids.append(item['contentDetails']['videoId'])
    
    request = youtube.playlistItems().list_next(request, first_response)
    while request:
        response = request.execute()
        for item in response['items']:
            video_ids.append(item['contentDetails']['videoId'])
        request = youtube.playlistItems().list_next(request, response)
    return (new_etag, video_ids)

def update_playlist_items(id):
    output_file = output_dir / f"{id}.json"
    data = json.loads(output_file.read_text())

    print(f"Update list {id} etag {data.get('items_etag')}")
    (new_etag, video_ids) = get_playlist_items(id, data.get('items_etag'))
    video_ids = video_ids or data['items']

    new_data = {
        'items_last_updated': batch_time.isoformat(),
        'items_etag': new_etag,
        'items': video_ids,
    }

    data.update(new_data);
    output_file.write_text(json.dumps(data, indent=2))

playlist_ids = retrieve_playlist()

existing_files = list(output_dir.glob('*.json'))
existing_ids = {f.stem for f in existing_files}
removed_ids = existing_ids - set(playlist_ids)
for playlist_id in sorted(removed_ids):
    archive_removed_playlist(playlist_id)

