from __future__ import annotations
from dataclasses import dataclass

from config import ROOT
from pprint import pprint
from datetime import datetime
import json
from util import to_obj, from_obj, dump_json
from context import Context

output_dir = ROOT / "data/youtube/channels/active"
archive_dir = ROOT / "data/youtube/channels/archive"

@dataclass
class Channel:
    """Represents a YouTube channe"""
    channel_id: str
    custom_url: str
    title: str
    banner_external_url: str
    description: str
    first_seen: datetime
    last_updated: datetime
    published_at: datetime
    playlists: dict
    statistics: dict
    status: dict
    thumbnails: dict
    topic_details: dict

    @classmethod
    def get(cls, channel_id) -> Channel:
        output_file = output_dir / f"{channel_id}.json"
        print(f"Looking for file {output_file}");
        if output_file.exists():
            print("data exist")
            data = json.loads(output_file.read_text())
        else:
            data = cls.update(channel_id)

        data['first_seen'] = datetime.fromisoformat(data['first_seen'])
        data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        data['published_at'] = datetime.fromisoformat(data['published_at'])

        return cls(**data)

    @classmethod
    def update(cls, id) -> dict:
        from youtube import get_youtube_client
        from deepdiff import DeepDiff

        output_file = output_dir / f"{id}.json"
        youtube = get_youtube_client()
        batch_time = Context.get().batch_time

        response = youtube.channels().list(
            part="brandingSettings,contentDetails,localizations,statistics,status,topicDetails,snippet",
            id=id,
            #mine=True,
        ).execute()
        item = to_obj(response['items'][0])

        #sections_response = youtube.channelSections().list(
        #    part="contentDetails,snippet",
        #    channelId=id,
        #).execute()
        #sections = sections_response['items']
        #pprint(sections)

        print(f"Update {id}")
        new_data = {
            'channel_id': item.id,
            'title': item.snippet.title,
            'banner_external_url': item.brandingSettings.image.bannerExternalUrl,
            'playlists': from_obj(item.contentDetails.relatedPlaylists),
            'custom_url': item.snippet.customUrl,
            'description': item.snippet.description,
            'published_at': datetime.fromisoformat(item.snippet.publishedAt).isoformat(),
            'thumbnails': from_obj(item.snippet.thumbnails),
            'statistics': from_obj(item.statistics),
            'status': from_obj(item.status),
            'topic_details': from_obj(item.topicDetails),
        }

        new_data_stamps = {
            'last_updated': batch_time.isoformat(),
        }

        if output_file.exists():
            data = json.loads(output_file.read_text())

            exclude_paths = [
                "root['first_seen']",
                "root['last_updated']",
            ]
            diff = DeepDiff(
                data, new_data,
                ignore_order=True,
                exclude_paths=exclude_paths,
            )
            if diff:
                #print("Would archive channel")
                #pprint(diff)
                cls.archive(data.copy())
                #return data
            else:
                print("No change")
        else:
            print(f"Created {id}");
            data = {'first_seen': batch_time.isoformat()}

        data.update(new_data)
        data.update(new_data_stamps)
        output_file.write_text(dump_json(data))

        return data

    @classmethod
    def archive(cls, data):
        batch_time = Context.get().batch_time
        year = batch_time.year
        week_number = batch_time.isocalendar()[1]
        slot_dir = archive_dir / str(year) / f"week-{week_number:02}"
        slot_dir.mkdir(parents=True, exist_ok=True)
        id = data['channel_id']
        archive_file = slot_dir / f"{id}.json"
        if archive_file.exists():
            return
        archive_file.write_text(dump_json(data))
