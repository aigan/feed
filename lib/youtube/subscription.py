from __future__ import annotations
from dataclasses import dataclass

from config import ROOT
from typing import Generator
from datetime import datetime
import json
from context import Context
from util import to_obj, from_obj, dump_json

data_dir = ROOT / "data/youtube/subscriptions/active"
archive_dir = ROOT / "data/youtube/subscriptions/archive"

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
    def get_all(cls) -> Generator[Subscription, None, None]:
        for path in data_dir.glob('*.json'):
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
        output_file = data_dir / f"{id}.json"
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
            data['first_seen'] = batch_time.isoformat(),

        output_file.write_text(dump_json(data))
        print(f"Wrote {id}");
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

        existing_files = list(data_dir.glob('*.json'))
        existing_ids = {f.stem for f in existing_files}
        unsubscribed = existing_ids - set(channel_ids)
        for channel_id in unsubscribed:
            cls.archive_unsubscribed(channel_id)


    @classmethod
    def archive_unsubscribed(cls, channel_id):
        batch_time = Context.get().batch_time
        year = batch_time.year

        src_file = data_dir / f"{channel_id}.json"
        if not src_file.exists():
            print(f"Warning: No active file for {channel_id}")
            return

        # Read and update data
        data = json.loads(src_file.read_text())
        data['unsubscribed_at'] = batch_time.isoformat()

        # Ensure archive directory exists
        year_dir = archive_dir / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        #print(f"Would archive {channel_id}")
        #return

        # Move to archive
        dest_file = year_dir / f"{channel_id}.json"
        dest_file.write_text(dump_json(data))
        src_file.unlink()

        print(f"Archived {channel_id}")
