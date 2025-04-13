from dataclasses import dataclass, fields
from typing import Optional

from util import to_obj, from_obj, dump_json, convert_fields, to_dict
from pprint import pprint
from datetime import datetime
from context import Context
from config import ROOT
import json

@dataclass
class Video:
    """Represents a YouTube video"""
    video_id: str
    title: str
    channel_id: str
    published_at: datetime
    first_seen: datetime
    last_updated: datetime
    description: str
    thumbnails_data: dict
    tags: list
    category_id: int
    live_status: str
    duration_data: str
    spatial_dimension_type: str
    resolution_tier: str
    captioned: bool
    licensed_content: bool
    content_rating_data: dict
    viewing_projection: str
    privacy_status: str
    license: str
    embeddable: bool
    public_stats_viewable: bool
    made_for_kids: bool
    view_count: int
    like_count: int
    comment_count: int
    topic_details: dict
    has_paid_product_placement: bool
    live_start: Optional[datetime] = None
    live_chat_id: Optional[str] = None
    recording_date: Optional[datetime] = None

    def transcript(self):
        from youtube import Transcript
        data_file = self.__class__.get_active_dir(self.video_id) / "transcript.json"
        if data_file.exists():
            return json.loads(data_file.read_text())
        transcript = Transcript.download(self.video_id)
        dump_json(data_file, transcript)
        return transcript

    @classmethod
    def get(cls, video_id):
        data_file = cls.get_active_dir(video_id) / "video.json"
        if data_file.exists():
            data = json.loads(data_file.read_text())
        else:
            data = cls.update(video_id)
        return cls(**convert_fields(cls, data))

    @classmethod
    def update(cls, video_id):
        from deepdiff import DeepDiff

        new_data = cls.retrieve(video_id)
        data_file = cls.get_active_dir(video_id) / "video.json"
        batch_time = Context.get().batch_time
        #print(data_file)

        if data_file.exists():
            data = json.loads(data_file.read_text())

            exclude_paths = [
                "root['first_seen']",
                "root['last_updated']",
                "root['view_count']",
                "root['like_count']",
                "root['comment_count']",
            ]
            diff = DeepDiff(
                data, new_data,
                ignore_order=True,
                exclude_paths=exclude_paths,
            )
            if diff:
                #pprint(diff)
                cls.archive(data.copy())
        else:
            data = {'first_seen': batch_time.isoformat()}

        data.update(new_data)
        data['last_updated'] =  batch_time.isoformat()
        dump_json(data_file, data)
        return data

    @classmethod
    def retrieve(cls, video_id):
        from youtube import get_youtube_client
        youtube = get_youtube_client()
        request = youtube.videos().list(
            id=video_id,
            part="snippet,contentDetails,liveStreamingDetails,paidProductPlacementDetails,recordingDetails,statistics,status,topicDetails",
        )
        response = request.execute()
        item = to_obj(response['items'][0])
        #pprint(item, width=120)
        #batch_time = Context.get().batch_time

        data = {
            'video_id': video_id,
            'title': item.snippet.title,
            'channel_id': item.snippet.channelId,
            'recording_date': item.recordingDetails.recordingDate,
            'published_at': item.snippet.publishedAt,
            'description': item.snippet.description,
            'thumbnails_data': item.snippet.thumbnails,
            'tags': item.snippet.tags,
            'category_id': item.snippet.categoryId,
            'live_start': item.liveStreamingDetails.scheduledStartTime,
            'live_chat_id': item.liveStreamingDetails.activeLiveChatId,
            'live_status': item.snippet.liveBroadcastContent,
            'duration_data': item.contentDetails.duration,
            'spatial_dimension_type': item.contentDetails.dimension,
            'resolution_tier': item.contentDetails.definition,
            'captioned': item.contentDetails.caption,
            'licensed_content': item.contentDetails.licensedContent,
            'content_rating_data': item.contentDetails.contentRating,
            'viewing_projection': item.contentDetails.projection,
            'privacy_status': item.status.privacyStatus,
            'license': item.status.license,
            'embeddable': item.status.embeddable,
            'public_stats_viewable': item.status.publicStatsViewable, # youtubeAnalytics
            'made_for_kids': item.status.madeForKids,
            'view_count': item.statistics.viewCount,
            'like_count': item.statistics.likeCount,
            'comment_count': item.statistics.commentCount,
            'topic_details': item.topicDetails,
            'has_paid_product_placement': item.paidProductPlacementDetails.hasPaidProductPlacement,
        }

        return to_dict(data)

    @classmethod
    def archive(cls, data):
        video_id = data['video_id']
        next_version = cls.latest_version(video_id) + 1
        archive_dir = cls.get_archive_dir(video_id)
        archive_file = archive_dir / f"v{next_version}.json"
        dump_json(archive_file, data)

    @classmethod
    def get_active_dir(cls, video_id):
        return ROOT / "data/youtube/videos/active" / video_id[:2] / video_id

    @classmethod
    def get_archive_dir(cls, video_id):
        return ROOT / "data/youtube/videos/archive" / video_id[:2] / video_id

    @classmethod
    def get_processed_dir(cls, video_id):
        return cls.get_active_dir(video_id) / 'processed'

    @classmethod
    def latest_version(cls, video_id):
        archive_dir = cls.get_archive_dir(video_id)
        version_files = archive_dir.glob("v*.json")
        return max(
            (int(f.stem[1:]) for f in version_files),
            default=0
        )
