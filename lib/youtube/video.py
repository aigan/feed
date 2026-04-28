import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pprint import pprint
from typing import Optional

import config
from context import Context
from util import convert_fields, dump_json, to_dict, to_obj


class VideoUnavailableError(Exception):
    pass


def _api_to_comment_dict(item, video_id, parent_id, total_reply_count):
    s = item['snippet']
    author_channel = s.get('authorChannelId')
    author_channel_id = author_channel.get('value') if isinstance(author_channel, dict) else None
    return {
        'comment_id': item['id'],
        'video_id': video_id,
        'parent_id': parent_id,
        'author_display_name': s.get('authorDisplayName', ''),
        'author_channel_id': author_channel_id,
        'text_display': s.get('textDisplay', ''),
        'text_original': s.get('textOriginal', ''),
        'like_count': int(s.get('likeCount', 0)),
        'published_at': s.get('publishedAt'),
        'updated_at': s.get('updatedAt'),
        'total_reply_count': total_reply_count,
    }


def _thread_to_comment_dicts(thread, video_id):
    snippet = thread['snippet']
    top = snippet['topLevelComment']
    yield _api_to_comment_dict(top, video_id, parent_id=None,
        total_reply_count=int(snippet.get('totalReplyCount', 0)))
    for reply in thread.get('replies', {}).get('comments', []):
        yield _api_to_comment_dict(reply, video_id,
            parent_id=reply['snippet']['parentId'], total_reply_count=0)


def _comment_header_line(c, indent, replies_present):
    parts = [
        f"[{c['comment_id']}]",
        c.get('author_display_name', ''),
        f"| {c.get('published_at', '')}",
        f"| likes: {c.get('like_count', 0)}",
    ]
    total = c.get('total_reply_count', 0) or 0
    if replies_present is not None and total > 0:
        parts.append(f"| replies: {replies_present}/{total}")
    return indent + ' '.join(parts)


def _render_comments_txt(comments_dict):
    top_level = sorted(
        (c for c in comments_dict.values() if c.get('parent_id') is None),
        key=lambda c: c.get('published_at') or '',
    )
    children = {}
    for c in comments_dict.values():
        pid = c.get('parent_id')
        if pid is None:
            continue
        children.setdefault(pid, []).append(c)
    for kids in children.values():
        kids.sort(key=lambda c: c.get('published_at') or '')

    lines = []
    for c in top_level:
        replies = children.get(c['comment_id'], [])
        lines.append(_comment_header_line(c, '', len(replies)))
        lines.append(c.get('text_display', ''))
        lines.append('')
        for r in replies:
            lines.append(_comment_header_line(r, '  ', None))
            body = r.get('text_display', '')
            lines.extend('  ' + ln for ln in body.split('\n'))
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


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

    @property
    def channel(self) -> 'Channel':
        from youtube import Channel
        return Channel.get(self.channel_id)

    @property
    def duration_seconds(self) -> int:
        """Get video duration in seconds."""
        try:
            import isodate
            duration = isodate.parse_duration(self.duration_data)
            return int(duration.total_seconds())
        except (AttributeError, ValueError, TypeError):
            return 0

    @property
    def duration_formatted(self) -> str:
        """Get video duration in human-readable format (HH:MM:SS or MM:SS)."""
        seconds = self.duration_seconds
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    def transcript(self, force=False):
        from youtube import Transcript, TranscriptMeta, TranscriptUnavailable
        active_dir = self.__class__.get_active_dir(self.video_id)
        data_file = active_dir / "transcript.json"
        meta = TranscriptMeta(active_dir)

        if not force:
            if meta.is_unavailable:
                return None
            if data_file.exists():
                return json.loads(data_file.read_text())

        print(f"download transcript {self.video_id}")
        try:
            data = Transcript.download(self.video_id)
        except TranscriptUnavailable as e:
            meta.mark_unavailable(e.reason)
            return None

        meta.clear_unavailable()
        dump_json(data_file, data)
        meta.stamp('transcript_downloaded_at')
        return data

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
        from youtube.client import execute_api
        youtube = get_youtube_client()
        request = youtube.videos().list(
            id=video_id,
            part="snippet,contentDetails,liveStreamingDetails,paidProductPlacementDetails,recordingDetails,statistics,status,topicDetails",
        )
        response = execute_api(request, 'videos.list')
        if not response.get('items'):
            raise VideoUnavailableError(video_id)
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
        return config.DATA_DIR / "youtube/videos/active" / video_id[:2] / video_id

    @classmethod
    def get_archive_dir(cls, video_id):
        return config.DATA_DIR / "youtube/videos/archive" / video_id[:2] / video_id

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

    @classmethod
    def get_active_comments_file(cls, video_id):
        return cls.get_active_dir(video_id) / 'comments.json'

    @classmethod
    def get_archive_comments_file(cls, video_id, version):
        return cls.get_archive_dir(video_id) / f'comments-v{version}.json'

    @classmethod
    def latest_comments_version(cls, video_id):
        archive_dir = cls.get_archive_dir(video_id)
        files = archive_dir.glob('comments-v*.json')
        return max(
            (int(f.stem.replace('comments-v', '')) for f in files),
            default=0,
        )

    def local_comments(self):
        from youtube.comment import Comment
        file = self.__class__.get_active_comments_file(self.video_id)
        if not file.exists():
            return []
        data = json.loads(file.read_text())
        return [
            Comment(**convert_fields(Comment, c))
            for c in data.get('comments', {}).values()
        ]

    def retrieve_comments(self, page_token=None):
        from googleapiclient.errors import HttpError

        from youtube import get_youtube_client
        from youtube.client import execute_api
        from youtube.comment import CommentsDisabledError

        youtube = get_youtube_client()
        kwargs = dict(
            videoId=self.video_id,
            part='snippet,replies',
            maxResults=100,
            textFormat='plainText',
        )
        if page_token:
            kwargs['pageToken'] = page_token
        request = youtube.commentThreads().list(**kwargs)
        try:
            while request:
                response = execute_api(request, 'commentThreads.list')
                yield response.get('items', []), response.get('nextPageToken')
                request = youtube.commentThreads().list_next(request, response)
        except HttpError as e:
            details = getattr(e, 'error_details', None) or []
            reasons = [d.get('reason', '') for d in details if isinstance(d, dict)]
            if e.resp.status == 403 and ('commentsDisabled' in reasons or 'commentsDisabled' in str(e)):
                raise CommentsDisabledError(self.video_id) from e
            raise

    def remote_comments(self, comment_limit=None, force=False):
        from youtube.comment import Comment

        resume_token = None
        pages_fetched_before = 0
        file = self.__class__.get_active_comments_file(self.video_id)
        if not force and file.exists():
            existing = json.loads(file.read_text())
            if existing.get('comments_disabled'):
                return
            if existing.get('fetch_complete', True):
                return
            resume_token = existing.get('next_page_token')
            pages_fetched_before = existing.get('pages_fetched', 0)

        buffer = []
        pages_this_run = 0
        next_token = resume_token
        completed = False
        try:
            for items, after_page_token in self.retrieve_comments(page_token=resume_token):
                for thread in items:
                    for comment_dict in _thread_to_comment_dicts(thread, self.video_id):
                        buffer.append(comment_dict)
                        yield Comment(**convert_fields(Comment, dict(comment_dict,
                            first_seen=Context.get().batch_time.isoformat(),
                            last_seen=Context.get().batch_time.isoformat())))
                pages_this_run += 1
                next_token = after_page_token
                if comment_limit is not None and len(buffer) >= comment_limit:
                    break
            completed = (next_token is None)
        finally:
            if pages_this_run > 0:
                fetch_state = {
                    'fetch_complete': completed,
                    'next_page_token': None if completed else next_token,
                    'pages_fetched': pages_fetched_before + pages_this_run,
                }
                self.update_comments_from_data(buffer, fetch_state)

    def update_comments_from_data(self, buffer, fetch_state):
        batch_time = Context.get().batch_time
        file = self.__class__.get_active_comments_file(self.video_id)

        existing = json.loads(file.read_text()) if file.exists() else {}
        existing_comments = existing.get('comments', {})
        merged = dict(existing_comments)
        for item in buffer:
            cid = item['comment_id']
            prior = existing_comments.get(cid) or {}
            merged[cid] = {
                **item,
                'first_seen': prior.get('first_seen', batch_time.isoformat()),
                'last_seen': batch_time.isoformat(),
                'replies_complete': prior.get('replies_complete', False),
            }

        new = {
            'comments_disabled': existing.get('comments_disabled', False),
            'fetched_at': batch_time.isoformat(),
            'fetch_complete': fetch_state['fetch_complete'],
            'next_page_token': fetch_state['next_page_token'],
            'pages_fetched': fetch_state['pages_fetched'],
            'comments': merged,
        }

        if existing_comments:
            self.archive_comments(existing, new)

        dump_json(file, new)
        txt_file = file.parent / 'comments.txt'
        txt_file.write_text(_render_comments_txt(merged))

    def archive_comments(self, old, new):
        from deepdiff import DeepDiff
        exclude_regex_paths = [
            r"root\['fetched_at'\]",
            r"root\['fetch_complete'\]",
            r"root\['next_page_token'\]",
            r"root\['pages_fetched'\]",
            r"root\['comments'\]\['[^']+'\]\['last_seen'\]",
            r"root\['comments'\]\['[^']+'\]\['like_count'\]",
            r"root\['comments'\]\['[^']+'\]\['total_reply_count'\]",
            r"root\['comments'\]\['[^']+'\]\['replies_complete'\]",
        ]
        diff = DeepDiff(old, new, ignore_order=True, exclude_regex_paths=exclude_regex_paths)
        if 'values_changed' not in diff:
            return
        version = self.__class__.latest_comments_version(self.video_id) + 1
        archive_file = self.__class__.get_archive_comments_file(self.video_id, version)
        dump_json(archive_file, old)

    def mirror_comments(self, comment_limit=None, force=False):
        from youtube.comment import CommentsDisabledError
        try:
            for _ in self.remote_comments(comment_limit=comment_limit, force=force):
                pass
        except CommentsDisabledError:
            self._mark_comments_disabled()

    def retrieve_thread_replies(self, comment_id):
        from youtube import get_youtube_client
        from youtube.client import execute_api

        youtube = get_youtube_client()
        request = youtube.comments().list(
            parentId=comment_id,
            part='snippet',
            maxResults=100,
            textFormat='plainText',
        )
        while request:
            response = execute_api(request, 'comments.list')
            for item in response.get('items', []):
                yield _api_to_comment_dict(item, self.video_id,
                    parent_id=item['snippet']['parentId'], total_reply_count=0)
            request = youtube.comments().list_next(request, response)

    def expand_replies(self, comment_id, force=False):
        file = self.__class__.get_active_comments_file(self.video_id)
        if not file.exists():
            raise ValueError(
                f'No comments cached for {self.video_id}; mirror first.'
            )
        existing = json.loads(file.read_text())
        existing_comments = existing.get('comments', {})
        target = existing_comments.get(comment_id)
        if not target:
            raise ValueError(
                f'Comment {comment_id} not in cache for {self.video_id}; '
                'mirror first or pass a known thread id.'
            )
        if target.get('parent_id') is not None:
            raise ValueError(
                f'Comment {comment_id} is a reply, not a top-level thread.'
            )
        if not force and target.get('replies_complete'):
            return

        replies = list(self.retrieve_thread_replies(comment_id))
        self._merge_thread_expansion(comment_id, replies)

    def _merge_thread_expansion(self, top_level_id, replies):
        batch_time = Context.get().batch_time
        file = self.__class__.get_active_comments_file(self.video_id)
        existing = json.loads(file.read_text())
        existing_comments = existing.get('comments', {})
        merged = dict(existing_comments)

        for item in replies:
            cid = item['comment_id']
            prior = existing_comments.get(cid) or {}
            merged[cid] = {
                **item,
                'first_seen': prior.get('first_seen', batch_time.isoformat()),
                'last_seen': batch_time.isoformat(),
                'replies_complete': False,
            }

        merged[top_level_id] = {
            **merged[top_level_id],
            'replies_complete': True,
        }

        new = {**existing, 'fetched_at': batch_time.isoformat(), 'comments': merged}
        self.archive_comments(existing, new)
        dump_json(file, new)
        txt_file = file.parent / 'comments.txt'
        txt_file.write_text(_render_comments_txt(merged))

    def _mark_comments_disabled(self):
        batch_time = Context.get().batch_time
        file = self.__class__.get_active_comments_file(self.video_id)
        existing = json.loads(file.read_text()) if file.exists() else {}
        existing.setdefault('comments', {})
        existing.update({
            'comments_disabled': True,
            'fetched_at': batch_time.isoformat(),
            'fetch_complete': True,
            'next_page_token': None,
            'pages_fetched': existing.get('pages_fetched', 0),
        })
        dump_json(file, existing)
        txt_file = file.parent / 'comments.txt'
        txt_file.write_text(_render_comments_txt(existing.get('comments', {})))
