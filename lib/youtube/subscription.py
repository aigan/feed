from __future__ import annotations
from dataclasses import dataclass

import config
from typing import Generator
from datetime import datetime
import json
from context import Context
from util import to_obj, from_obj, dump_json
from pprint import pprint

@dataclass
class Subscription:
    """Represents a YouTube subscription"""
    channel_id: str
    subscription_id: str
    first_seen: datetime
    last_updated: datetime
    activity_type: str
    new_item_count: int
    total_item_count: int
    title: str
    
    @property
    def channel(self) -> Channel:
        from youtube import Channel
        return Channel.get(self.channel_id)

    @classmethod
    def data_dir(cls):
        return config.DATA_DIR / "youtube/subscriptions/active"

    @classmethod
    def archive_dir(cls):
        return config.DATA_DIR / "youtube/subscriptions/archive"

    @classmethod
    def get_all(cls) -> Generator[Subscription, None, None]:
        for path in cls.data_dir().glob('*.json'):
            data = json.loads(path.read_text())
            data['first_seen'] = datetime.fromisoformat(data['first_seen'])
            data['last_updated'] = datetime.fromisoformat(data['last_updated'])
            yield cls(**data)

    @classmethod
    def get_hot(cls) -> Generator[Subscription, None, None]:
        from youtube import get_youtube_client
        youtube = get_youtube_client()
        request = youtube.subscriptions().list(
            part="contentDetails,snippet",
            mine=True,
        )

        while request:
            response = request.execute()
            for item in to_obj(response['items']):
                data = cls.update_from_data(item)
                yield cls(**data)
            request = youtube.subscriptions().list_next(request, response)

    @classmethod
    def update_from_data(cls, item) -> dict:
        id = item.snippet.resourceId.channelId
        output_file = cls.data_dir() / f"{id}.json"
        batch_time = Context.get().batch_time

        new_data = {
            'channel_id': id,
            'title': item.snippet.title,
            'subscription_id': item.id,
            'last_updated': batch_time.isoformat(),
            'activity_type': item.contentDetails.activityType,
            'new_item_count': item.contentDetails.newItemCount,
            'total_item_count': item.contentDetails.totalItemCount
        }

        if output_file.exists():
            data = json.loads(output_file.read_text())
            data.update(new_data)
        else:
            data = new_data
            data['first_seen'] = batch_time.isoformat()

        dump_json(output_file, data)
        #print(f"Wrote {id}");
        return data

    @classmethod
    def update_all(cls):
        from youtube import get_youtube_client
        youtube = get_youtube_client()
        request = youtube.subscriptions().list(
            part="contentDetails,snippet",
            order="alphabetical",
            mine=True,
            maxResults=50
        )

        channel_ids = []
        while request:
            response = request.execute()
            for item in to_obj(response['items']):
                data = cls.update_from_data(item)
                channel_ids.append(data['channel_id'])
            request = youtube.subscriptions().list_next(request, response)
            #request = False

        existing_files = list(cls.data_dir().glob('*.json'))
        existing_ids = {f.stem for f in existing_files}
        unsubscribed = existing_ids - set(channel_ids)
        for channel_id in unsubscribed:
            cls.archive_unsubscribed(channel_id)


    @classmethod
    def archive_unsubscribed(cls, channel_id):
        batch_time = Context.get().batch_time
        year = batch_time.year

        src_file = cls.data_dir() / f"{channel_id}.json"
        if not src_file.exists():
            print(f"Warning: No active file for {channel_id}")
            return

        data = json.loads(src_file.read_text())
        data['unsubscribed_at'] = batch_time.isoformat()

        year_dir = cls.archive_dir() / str(year)
        dest_file = year_dir / f"{channel_id}.json"
        dump_json(dest_file, data)
        src_file.unlink()

        print(f"Archived {channel_id}")
