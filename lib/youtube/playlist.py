from __future__ import annotations
from dataclasses import dataclass, fields

from util import to_obj, from_obj, dump_json
from pprint import pprint
from typing import Generator
from context import Context
from pathlib import Path
from datetime import datetime
import json

@dataclass
class Playlist:
    """Represents a YouTube playlist"""
    first_seen: datetime
    playlist_id: str
    channel_id: str
    title: str
    etag: str
    published_at: datetime
    item_count: int
    privacy_status: str
    description: str
    thumbnails: dict
    items_etag: str
    items: list
    last_updated: datetime
    items_last_updated: datetime

    @classmethod
    def for_channel(cls, channel_id) -> Generator[Playlist, None, None]:
        if cls.get_active_dir(channel_id).is_dir():
            itr = cls.local_for_channel(channel_id)
        else:
            itr = cls.remote_for_channel(channel_id)
            
        for data in itr:
            for field in fields(cls):
                if field.name in data and field.type == datetime:
                    data[field.name] = datetime.fromisoformat(data[field.name])
            yield cls(**data)
            
    @classmethod
    def local_for_channel(cls, channel_id) -> Generator[dict, None, None]:
        data_dir = cls.get_active_dir(channel_id)
        for path in data_dir.glob('*.json'):
            yield json.loads(path.read_text())
            
    @classmethod
    def remote_for_channel(cls, channel_id) -> Generator[dict, None, None]:
        data_dir = cls.get_active_dir(channel_id)
        playlist_ids = []
        for item in cls.retrieve(channel_id):
            yield cls.update_from_data(item)
            playlist_ids.append(item.id)
        existing_files = list(data_dir.glob('*.json'))
        existing_ids = {f.stem for f in existing_files}
        removed_ids = existing_ids - set(playlist_ids)
        for playlist_id in sorted(removed_ids):
            cls.archive_removed(channel_id, playlist_id)

    @classmethod
    def update_from_data(cls, item):
        batch_time = Context.get().batch_time
        playlist_id = item.id
        channel_id = item.snippet.channelId
        data_file = cls.get_active_dir(channel_id) / f"{playlist_id}.json"
        new_data = {
            'playlist_id': playlist_id,
            'channel_id': channel_id,
            'title': item.snippet.title,
            'etag': item.etag,
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

        if data_file.exists():
            data = json.loads(data_file.read_text())
            (new_items_etag, video_ids) = cls.retrieve_playlist_items(
                playlist_id, data.get('items_etag')
            )

            # etag depends on parts requested
            if data.get('etag') == item.etag and data.get('items_etag') == new_items_etag:
                return data
            #print(f"Update {playlist_id}")

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
                cls.archive(data.copy())
        else:
            #print(f"Created {playlist_id}");
            (new_items_etag, video_ids) = cls.retrieve_playlist_items(playlist_id)
            new_data['items_etag'] = new_items_etag
            new_data['items'] = video_ids
            data = {'first_seen': batch_time.isoformat()}

        data.update(new_data)
        data.update(new_data_stamps)
        dump_json(data_file, data)
        return data


    @classmethod
    def retrieve(cls, channel_id) -> Generator[SafeNamespace, None, None]:
        from youtube import get_youtube_client
        youtube = get_youtube_client()
        request = youtube.playlists().list(
            part="id,contentDetails,status,snippet",
            channelId=channel_id
        )

        while request:
            response = request.execute()
            for item in to_obj(response['items']):
                yield item
            request = youtube.playlists().list_next(request, response)
    
    @classmethod
    def retrieve_playlist_items(cls, playlist_id, etag=None):
        from youtube import get_youtube_client
        youtube = get_youtube_client()
        request = youtube.playlistItems().list(
            playlistId=playlist_id,
            part="contentDetails",
            maxResults=50,
        )

        first_response = request.execute()
        new_etag = first_response['etag']

        if etag and etag == new_etag:
            #print(f"List {playlist_id} unchanged")
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

    @classmethod
    def archive_removed(cls, channel_id, playlist_id):
        batch_time = Context.get().batch_time
        data_file = cls.get_active_dir(channel_id) / f"{playlist_id}.json"
        data = json.loads(output_file.read_text())
        data['removed_at'] = batch_time.isoformat()
        cls.archive_by_data(data)
        output_file.unlink()
        print(f"Archived {playlist_id}")

    @classmethod
    def archive_by_data(cls, data):
        channel_id = data['channel_id']
        playlist_id = data['playlist_id']
        batch_time = Context.get().batch_time
        year = batch_time.year
        week_number = batch_time.isocalendar()[1]
        slot_dir = cls.get_archive_dir(channel_id) / str(year) / f"week-{week_number:02}"
        archive_file = slot_dir / f"{playlist_id}.json"
        if archive_file.exists():
            old_data = json.loads(archive_file.read_text())
            data['items'] = cls.merge_ordered(old_data['items'], data['items'])
            data.pop('items_etag')
            dump_json(archive_file, data)

    @classmethod
    def merge_ordered(cls, old, new):
        """Merge new into old, preserving order as much as possible."""
        from difflib import SequenceMatcher
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
            
    @classmethod
    def get_active_dir(cls, channel_id) -> Path:
        from youtube import Channel
        return Channel.get_active_dir(channel_id) / "playlists"

    @classmethod
    def get_archive_dir(cls, channel_id) -> Path:
        from youtube import Channel
        return Channel.get_archive_dir(channel_id) / "playlists"

    
