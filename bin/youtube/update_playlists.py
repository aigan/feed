#!/bin/env python
from youtube import get_youtube_client
from pprint import pprint
from datetime import datetime, timezone
from config import ROOT
from util import to_obj, dump_json
from pathlib import Path
import json

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
        
            if output_file.exists():
                data = json.loads(output_file.read_text())
                (new_items_etag, video_ids) = get_playlist_items(id, data.get('items_etag'))
                # etag depends on parts requested
                if data.get('etag') == item.etag and data.get('items_etag') == new_items_etag:
                    continue
                print(f"Update {id}");
            else:
                print(f"Created {id}");
                (new_items_etag, video_ids) = get_playlist_items(id)
                data = {
                    'first_seen': batch_time.isoformat(),
                }

            video_ids = video_ids or data['items']
            #pprint(item.snippet)
            
            new_data = {
                'playlist_id': id,
                'title': item.snippet.title,
                'last_updated': batch_time.isoformat(),
                'etag': item.etag,
                'channel_id': item.snippet.channelId,
                'published_at': datetime.fromisoformat(item.snippet.publishedAt).isoformat(),
                'item_count': item.contentDetails.itemCount,
                'privacy_status': item.status.privacyStatus,
                'description': item.snippet.description,
                'thumbnails': item.snippet.thumbnails,
                'items_last_updated': batch_time.isoformat(),
                'items_etag': new_items_etag,
                'items': video_ids,
            }

            data.update(new_data);
            output_file.write_text(dump_json(data))
            
        request = youtube.playlists().list_next(request, response)
        #request = False

    return playlist_ids;


#def archive_unliked_videos(unliked_ids, batch_time):
#    archive_base = ROOT / "data/youtube/likes/archive"
#    year = batch_time.year
#    
#    for video_id in unliked_ids:
#        src_file = output_dir / f"{video_id}.json"
#        if not src_file.exists():
#            print(f"Warning: No active file for {video_id}")
#            continue
#            
#        # Read and update data
#        data = json.loads(src_file.read_text())
#        data['unliked_at'] = batch_time.isoformat()
#        
#        # Ensure archive directory exists
#        year_dir = archive_base / str(year)
#        year_dir.mkdir(parents=True, exist_ok=True)
#        
#        # Move to archive
#        dest_file = year_dir / f"{video_id}.json"
#        dest_file.write_text(json.dumps(data, indent=2))
#        src_file.unlink()
#        
#        print(f"Archived {video_id}")

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
#removed_ids = existing_ids - set(playlist_ids)
#pprint(removed_ids)
# TODO: archive removed playlists

for playlist_id in sorted(existing_ids):
#    print(f"Update list {playlist_id}")
#    get_playlist_items(playlist_id)
#    #update_playlist_items(playlist_id)
    break


#update_playlist_items("PLbvfm0ge12qmi7NLm_3a6lRvhsqhrvfe-")

