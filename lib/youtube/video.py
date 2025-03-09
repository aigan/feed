from dataclasses import dataclass, fields
from typing import Optional

from util import to_obj, from_obj, dump_json, convert_fields
from pprint import pprint
from datetime import datetime
from context import Context

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

    @classmethod
    def get(cls, video_id):
        data = cls.retrieve(video_id)
        return cls(**data)

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
        batch_time = Context.get().batch_time

        new_data = {
            'video_id': video_id,
            'title': item.snippet.title,
            'channel_id': item.snippet.channelId,
            'recording_date': item.recordingDetails.recordingDate,
            'published_at': item.snippet.publishedAt,
            'first_seen': batch_time.isoformat(),
            'last_updated': batch_time.isoformat(),
            'description': item.snippet.description,
            'thumbnails_data': from_obj(item.snippet.thumbnails),
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
            'content_rating_data': from_obj(item.contentDetails.contentRating),
            'viewing_projection': item.contentDetails.projection,
            'privacy_status': item.status.privacyStatus,
            'license': item.status.license,
            'embeddable': item.status.embeddable,
            'public_stats_viewable': item.status.publicStatsViewable, # youtubeAnalytics
            'made_for_kids': item.status.madeForKids,
            'view_count': item.statistics.viewCount,
            'like_count': item.statistics.likeCount,
            'comment_count': item.statistics.commentCount,
            'topic_details': from_obj(item.topicDetails),
            'has_paid_product_placement': item.paidProductPlacementDetails.hasPaidProductPlacement,
        }

        return convert_fields(cls, new_data)
