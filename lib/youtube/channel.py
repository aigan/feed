from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from config import ROOT
from pprint import pprint
from datetime import datetime, timedelta
import json
from util import to_obj, from_obj, dump_json, convert_fields, to_dict
from context import Context

SCHEMA_VERSION = 2

@dataclass
class Channel:
    """Represents a YouTube channel"""
    channel_id: str
    custom_url: str
    title: str
    banner_external_url: str
    description: str
    first_seen: datetime
    last_updated: datetime
    published_at: datetime
    playlists_data: dict
    view_count: int
    subscriber_count: int
    uploads_count: int
    status: dict
    thumbnails: dict
    topic_details: dict
    schema_version: int
    #last_uploads_mirror: Optional[datetime] = None

    @property
    def playlists(self) -> List[Playlist]:
        from youtube import Playlist
        return Playlist.for_channel(self.channel_id)

    @property
    def local_uploads_count(self) -> int:
        uploads_dir = self.get_active_dir(self.channel_id) / "uploads"
        count = 0;
        for path in uploads_dir.glob('*.json'):
            data = json.loads(path.read_text())
            count += len(data)
        return count

    @classmethod
    def get(cls, channel_id) -> Channel:
        data_file = cls.get_active_dir(channel_id) / "channel.json"

        if data_file.exists():
            data = json.loads(data_file.read_text())
            if data.get('schema_version', 0) >= SCHEMA_VERSION:
                return cls(**convert_fields(cls,data))

        data = cls.update(channel_id)
        return cls(**convert_fields(cls,data))

    def sync(self):
        batch_time = Context.get().batch_time
        age = batch_time - self.last_updated
        if age > timedelta(days=1):
            data = self.__class__.update(self.channel_id)
            record =  convert_fields(self.__class__, data)
            for field, value in record.items():
                if hasattr(self, field):
                    setattr(self, field, value)
        return self

#    def get_uploads(self) -> Generator[Video, None, None]:
#        # TODO: check age of local file or dir
#        first_local = next(local_videos)
#        first_time = first_local.published_at
#        print(f"First is {first_time}");
#        for video in self.remote_uploads():
#            yield video

    def local_uploads(self) -> Generator[Video, None, None]:
        from youtube import Video
        uploads_dir = self.get_active_dir(self.channel_id) / "uploads"
        for path in sorted(uploads_dir.glob('*.json'), reverse=True):
            data = json.loads(path.read_text())
            for (video_id, published_at_data) in data:
                published_at = datetime.fromisoformat(published_at_data)
                yield Video.get(video_id)

    def remote_uploads(self) -> Generator[Video, None, None]:
        from youtube import Video
        buffer_year = None
        buffer_data = []
        try:
            for item in self.retrieve_uploads():
                video_id = item['contentDetails']['videoId']
                published_at = datetime.fromisoformat(item['contentDetails']['videoPublishedAt'])
                year = published_at.year

                if buffer_year and year != buffer_year:
                    self.update_uploads_from_data(buffer_data)
                    buffer_data = []

                buffer_year = year
                buffer_data.append((video_id, published_at))

                yield Video.get(video_id)
        finally:
            if buffer_year and buffer_data:
                self.update_uploads_from_data(buffer_data)

    def retrieve_uploads(self) -> Generator[dict, None, None]:
        from youtube import get_youtube_client
        youtube = get_youtube_client()
        playlist_id = self.playlists_data['uploads']
        request = youtube.playlistItems().list(
            playlistId=playlist_id,
            part="contentDetails",
            maxResults=50
        )
        while request:
            response = request.execute()
            #print(f"Batch with {len(response['items'])}")
            for item in response['items']:
                yield item
            request = youtube.playlistItems().list_next(request, response)

    def update_uploads_from_data(self, buffer_data):
        batch_time = Context.get().batch_time
        year = buffer_data[0][1].year
        data_file = self.get_active_uploads_file(year)
        #print(f"Should save {len(buffer_data)} in {data_file}")
        new_videos = [(video_id, published_at.isoformat()) for video_id, published_at in buffer_data]

        if data_file.exists():
            existing_videos = json.loads(data_file.read_text())
            self.archive_uploads(existing_videos, new_videos)

            last_new_video_date = new_videos[-1][1]
            older_videos = [v for v in existing_videos if v[1] < last_new_video_date]

            final_videos = new_videos + older_videos
        else:
            final_videos = new_videos

        dump_json(data_file, final_videos)

    def archive_uploads(self, old, new):
        from difflib import SequenceMatcher

        old_ids = [v[0] for v in old]
        new_ids = [v[0] for v in new]

        matcher = SequenceMatcher(None, old_ids, new_ids)
        need_archive = any(tag in ('replace', 'delete') for tag, i1, i2, j1, j2 in matcher.get_opcodes())

        if not need_archive: return

        video_dict = {}

        for video in old:
            video_dict[video[0]] = video

        for video in new:
            video_dict[video[0]] = video

        combined_videos = list(video_dict.values())
        combined_videos.sort(key=lambda x: x[1], reverse=True)

        year = datetime.fromisoformat(new[0][1]).year
        archive_file = self.get_archive_uploads_file(year)
        dump_json(archive_file, combined_videos)

    def mirror_uploads(self):
        """Mirror all channel uploads to local storage"""
        sync_file = self.get_active_dir(self.channel_id) / "uploads.json"
        if sync_file.exists():
            self.fetch_recent_uploads()
        else:
            self.fetch_all_uploads()

    def sync_record(self):
        batch_time = Context.get().batch_time
        defaults = {
            'first_updated': batch_time.isoformat(),
            'last_uploads_mirror': None,
            'last_uploads_sync': None,
        }

        sync_file = self.get_active_dir(self.channel_id) / "uploads.json"
        if sync_file.exists():
            data =  json.loads(sync_file.read_text())
            return to_obj(convert_fields(dict, {**defaults, **data}))
        else:
            return to_obj(convert_fields(dict, defaults))

    def sync_record_save(self, data):
        sync_file = self.get_active_dir(self.channel_id) / "uploads.json"
        # Temporary workaround. ... Should use utils for conversion
        data_dict = {
            'first_updated': data.first_updated.isoformat() if hasattr(data.first_updated, 'isoformat') else data.first_updated,
            'last_uploads_mirror': data.last_uploads_mirror.isoformat() if hasattr(data.last_uploads_mirror, 'isoformat') else data.last_uploads_mirror,
            'last_uploads_sync': data.last_uploads_sync.isoformat() if hasattr(data.last_uploads_sync, 'isoformat') else data.last_uploads_sync,
        }
        dump_json(sync_file, data_dict)

    def fetch_all_uploads(self):
        self.sync()
        print(f"Uploaded {self.uploads_count} videos")
        count = 0
        for video in self.remote_uploads():
            count += 1
            print(f"Video {count} of {self.uploads_count} at {video.published_at}: {video.title}")
            if count == 1:
                latest_video_date = video.published_at
        sync_data = self.sync_record()
        batch_time = Context.get().batch_time
        sync_data.last_uploads_mirror = batch_time
        sync_data.last_uploads_sync = latest_video_date or batch_time
        self.sync_record_save(sync_data)

    def fetch_recent_uploads(self):
        sync_data = self.sync_record()
        last_sync = sync_data.last_uploads_sync
        if last_sync is None:
            return self.fetch_all_uploads()
        #try:
        #    last_video = next(self.local_uploads())
        #except StopIteration:
        #    return self.fetch_all_uploads()
        print(f"Sync to {last_sync}")
        for video in self.remote_uploads():
            print(f"Video {video.published_at}: {video.title}")
            if latest_video_date is None:
                latest_video_date = video.published_at
            if video.published_at < last_sync:
                break
        sync_data = self.sync_record()
        batch_time = Context.get().batch_time
        sync_data.last_uploads_sync = latest_video_date or batch_time
        self.sync_record_save(sync_data)

    @classmethod
    def retrieve(cls, channel_id) -> dict:
        from youtube import get_youtube_client
        youtube = get_youtube_client()

        response = youtube.channels().list(
            part="brandingSettings,contentDetails,localizations,statistics,status,topicDetails,snippet",
            id=channel_id,
        ).execute()
        item = to_obj(response['items'][0])

        #sections_response = youtube.channelSections().list(
        #    part="contentDetails,snippet",
        #    channelId=id,
        #).execute()
        #sections = sections_response['items']
        #pprint(sections)

        data = {
            'channel_id': item.id,
            'title': item.snippet.title,
            'schema_version': SCHEMA_VERSION,
            'banner_external_url': item.brandingSettings.image.bannerExternalUrl,
            'playlists_data': item.contentDetails.relatedPlaylists,
            'custom_url': item.snippet.customUrl,
            'description': item.snippet.description,
            'published_at': datetime.fromisoformat(item.snippet.publishedAt).isoformat(),
            'thumbnails': item.snippet.thumbnails,
            'view_count': item.statistics.viewCount,
            'subscriber_count': item.statistics.subscriberCount,
            'uploads_count': item.statistics.videoCount,
            'status': item.status,
            'topic_details': item.topicDetails,
        }

        return to_dict(data)


    @classmethod
    def update(cls, channel_id) -> dict:
        from deepdiff import DeepDiff

        print("Update channel")
        batch_time = Context.get().batch_time
        new_data = cls.retrieve(channel_id)
        output_file = cls.get_active_dir(channel_id) / "channel.json"

        if output_file.exists():
            data = json.loads(output_file.read_text())
            if data.get('schema_version', 0) < SCHEMA_VERSION:
                data = cls.migrate(data)
            cls.archive(data, new_data)

        else:
            data = {'first_seen': batch_time.isoformat()}

        data.update(new_data)
        data['last_updated'] =  batch_time.isoformat()
        dump_json(output_file, data)
        return data

    @classmethod
    def archive(cls, old, new):
        from deepdiff import DeepDiff

        exclude_paths = [
            "root['first_seen']",
            "root['last_updated']",
            #"root['last_uploads_mirror']",
        ]
        diff = DeepDiff(
            old, new,
            ignore_order=True,
            exclude_paths=exclude_paths,
        )

        if not diff: return

        id = old['channel_id']
        archive_file = cls.get_archive_dir(id) / "channel.json"
        if archive_file.exists(): return
        dump_json(archive_file, old)

    @classmethod
    def get_active_dir(cls, channel_id) -> Path:
        data_dir = ROOT / "data/youtube/channels/active"
        return data_dir / channel_id

    @classmethod
    def get_archive_dir(cls, channel_id) -> Path:
        batch_time = Context.get().batch_time
        year = batch_time.year
        week_number = batch_time.isocalendar()[1]
        archive_dir = ROOT / "data/youtube/channels/archive"
        return archive_dir / str(year) / f"week-{week_number:02}" / channel_id

    def get_active_uploads_file(self, year) -> Path:
        return self.get_active_dir(self.channel_id) / f"uploads/{str(year)}.json"

    def get_archive_uploads_file(self, year) -> Path:
        return self.get_archive_dir(self.channel_id) / f"uploads/{str(year)}.json"

    @classmethod
    def migrate(cls, data):
        MIGRATIONS = {
            0: cls.migrate_v1,
            1: cls.migrate_v1,
        }

        print("Migrate data")
        current = data.get('schema_version', 0)
        func = MIGRATIONS.get(current)
        return func(data)

    @classmethod
    def migrate_v1(cls, data):
        result = data.copy()
        result.pop('last_uploads_mirror', None)
        result.pop('statistics', None)
        result['uploads_count'] = result.pop('video_count', None)
        result['schema_version'] = 2
        return result
