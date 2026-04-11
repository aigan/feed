from datetime import datetime

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import IpBlocked, RequestBlocked

from rate_limiter import RateLimiter
from rate_limits import YOUTUBE_TIMEDTEXT


class TranscriptUnavailable(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _run_timedtext(video_id, fn):
    """Run a timedtext API call under the rate limiter, mapping errors."""
    ticket = RateLimiter.get().acquire(YOUTUBE_TIMEDTEXT)
    try:
        result = fn()
    except (IpBlocked, RequestBlocked) as e:
        ticket.blocked()
        print(f'[blocked] {video_id}: {e}')
        raise
    except Exception as e:
        ticket.error(e)
        raise TranscriptUnavailable(type(e).__name__) from e
    ticket.ok()
    return result


class Transcript:
    """Represents a Youtube transcript"""

    @classmethod
    def get_best(cls, video_id):
        def _list():
            ytt_api = YouTubeTranscriptApi()
            return list(ytt_api.list(video_id))

        available_transcripts = _run_timedtext(video_id, _list)

        english_variants = [t for t in available_transcripts
            if t.language_code.startswith('en')]

        if english_variants:
            manual_transcripts = [t for t in english_variants if not t.is_generated]
            if manual_transcripts:
                transcript = manual_transcripts[0]
            else:
                transcript = english_variants[0]
        else:
            transcript = available_transcripts[0]

        print(f'Selected transcript: {transcript.language_code} ({transcript.language})')
        return transcript

    @classmethod
    def download(cls, video_id):
        transcript = cls.get_best(video_id)
        transcript_data = _run_timedtext(video_id, transcript.fetch)

        segments = transcript_data.to_raw_data()

        return {
            "metadata": {
                "language": transcript.language,
                "language_code": transcript.language_code,
                "is_generated": transcript.is_generated,
                "segment_count": len(transcript_data),
                "video_id": video_id,
                "downloaded_at": datetime.now().isoformat()
            },
            "segments": segments
        }

    @classmethod
    def process_timestamps(cls, description: str) -> str:
        import re
        timestamp_pattern = re.compile(r'^(\d+:(?:\d+:)?\d+)(.*?)$', re.MULTILINE)

        def replace_timestamp(match):
            timestamp = match.group(1)
            rest_of_line = match.group(2)

            # Convert timestamp to seconds
            parts = timestamp.split(':')
            if len(parts) == 2:  # M:SS or MM:SS
                minutes, seconds = map(int, parts)
                total_seconds = minutes * 60 + seconds
            elif len(parts) == 3:  # H:MM:SS
                hours, minutes, seconds = map(int, parts)
                total_seconds = hours * 3600 + minutes * 60 + seconds
            else:
                return match.group(0)  # Return unchanged if format not recognized

            # Format the new line with second offset
            return f"[ts {total_seconds}] {timestamp}{rest_of_line}"

        # Apply the replacement
        processed_description = timestamp_pattern.sub(replace_timestamp, description)

        return processed_description
