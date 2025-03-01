from __future__ import annotations
from config import ROOT
from dataclasses import dataclass
from datetime import datetime
import json

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
    def get_all(cls) -> list[Subscription]:
        data_dir = ROOT / "data/youtube/subscriptions/active"
        result = []
        for path in data_dir.glob('*.json'):
            data = json.loads(path.read_text())
            data['first_seen'] = datetime.fromisoformat(data['first_seen'])
            data['last_updated'] = datetime.fromisoformat(data['last_updated'])
            result.append(cls(**data))
        return result
            


    
