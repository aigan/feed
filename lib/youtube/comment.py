from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from util import convert_fields


class CommentsDisabledError(Exception):
    pass


@dataclass
class Comment:
    """Represents a single YouTube comment (top-level thread or reply)."""
    comment_id: str
    video_id: str
    parent_id: Optional[str]
    author_display_name: str
    author_channel_id: Optional[str]
    text_display: str
    text_original: str
    like_count: int
    published_at: datetime
    updated_at: datetime
    total_reply_count: int
    first_seen: datetime
    last_seen: datetime
    replies_complete: bool = False

    @property
    def is_top_level(self) -> bool:
        return self.parent_id is None

    def replies(self) -> list[Comment]:
        from youtube.video import Video
        file = Video.get_active_comments_file(self.video_id)
        if not file.exists():
            return []
        data = json.loads(file.read_text())
        return [
            Comment(**convert_fields(Comment, c))
            for c in data.get('comments', {}).values()
            if c.get('parent_id') == self.comment_id
        ]
