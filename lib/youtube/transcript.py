from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime
from pprint import pprint

class Transcript:
    """Represents a Youtube transcript"""

    @classmethod
    def get_best(cls, video_id):
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Get all available transcript languages
            available_transcripts = list(transcript_list)

            # Print available options for debugging
            print("Available transcripts:")
            for t in available_transcripts:
                print(f"{t.language_code}: {t.language} (Auto-generated: {t.is_generated})")

            # Prioritize English variants
            english_variants = [t for t in available_transcripts
                if t.language_code.startswith('en')]

            if english_variants:
                # Prefer manually created over auto-generated
                manual_transcripts = [t for t in english_variants if not t.is_generated]
                if manual_transcripts:
                    transcript = manual_transcripts[0]
                else:
                    transcript = english_variants[0]
            else:
                # No English transcript, take the first available
                transcript = available_transcripts[0]

            print(f"Selected transcript: {transcript.language_code} ({transcript.language})")
            return transcript

        except Exception as e:
            print(f"Error getting transcript: {e}")
            return None

    @classmethod
    def download(cls, video_id):
        transcript = cls.get_best(video_id)
        if transcript == None:
            return None

        transcript_data = transcript.fetch()

        print(f"Transcript language: {transcript.language}")
        print(f"Transcript is generated: {transcript.is_generated}")
        print(f"Found {len(transcript_data)} transcript segments")

        # Print first few segments as example
        print("\nSample of transcript content:")
        for segment in transcript_data[:3]:
            pprint(segment)

        # Use the built-in to_raw_data method to convert to JSON-serializable format
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
