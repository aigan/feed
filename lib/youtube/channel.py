from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Channel:
    """Represents a YouTube channe"""
    channel_id: str
    title: str

    @classmethod
    def get(cls, channel_id) -> Channel:
        return cls(
            channel_id=channel_id,
            title="test",
        )
