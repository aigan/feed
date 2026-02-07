#!/usr/bin/env python3
from youtube_transcript_api import YouTubeTranscriptApi
import json
from pprint import pprint
import sys
from datetime import datetime

def download_transcript(video_id):
    try:
        # Get available transcript list
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        pprint(transcript_list)
        for transcript in transcript_list:
            print(f"Language: {transcript.language} ({transcript.language_code}) Is auto-generated: {transcript.is_generated}")


        return None

        # Try to get auto-generated transcript first
        try:
            transcript = transcript_list.find_generated_transcript(['en'])
            print(f"Found auto-generated transcript")
        except:
            # Fall back to any available transcript
            print(f"No auto-generated transcript, trying manual transcripts")
            transcript = transcript_list.find_transcript(['en'])
        
        # Fetch the actual transcript data
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
    
    except Exception as e:
        print(f"Error downloading transcript: {str(e)}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcript_test.py VIDEO_ID")
        sys.exit(1)
    
    video_id = sys.argv[1]
    print(f"Attempting to download transcript for video ID: {video_id}")
    
    transcript_result = download_transcript(video_id)
    
    if transcript_result:
        # Save to file for inspection
        with open(f"{video_id}_transcript.json", "w") as f:
            json.dump(transcript_result, f, indent=2)
        print(f"\nTranscript saved to {video_id}_transcript.json")
