from __future__ import annotations
from dataclasses import dataclass

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
    
    @classmethod
    def get_all(cls) -> Generator[Subscription, None, None]:
        from typing import Generator
        from config import ROOT
        from datetime import datetime
        import json

        data_dir = ROOT / "data/youtube/subscriptions/active"
        result = []
        for path in data_dir.glob('*.json'):
            data = json.loads(path.read_text())
            data['first_seen'] = datetime.fromisoformat(data['first_seen'])
            data['last_updated'] = datetime.fromisoformat(data['last_updated'])
            yield cls(**data)

    @property
    def channel(self) -> Channel:
        from youtube import Channel
        return Channel.get(self.channel_id)
    
