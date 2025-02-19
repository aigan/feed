#!/bin/env python
from youtube import get_youtube_client
from pprint import pprint
from datetime import datetime, timezone
from config import ROOT
from pathlib import Path
import json

batch_time = datetime.now(timezone.utc)
output_dir = ROOT / "data/youtube/likes/active"
log_file = ROOT / "data/youtube/likes/likes.log"


def retrieve_list():
    youtube = get_youtube_client()
    request = youtube.videos().list(
        part="id",
        myRating="like",
        maxResults=20
    )
    video_ids = []
    
    while request:
        response = request.execute()
        found_existing = False
        
        for video in response['items']:
            video_ids.append(video['id']);
            output_file = output_dir / f"{video['id']}.json"
        
            if output_file.exists():
                #print(f"Skipped {video['id']}");
                found_existing = True
                continue
            
            video_data = {
                'first_seen': batch_time.isoformat(),
                'video': video
            }
            
            output_file.write_text(json.dumps(video_data, indent=2))
            
            with log_file.open('a') as f:
                f.write(f"{batch_time.isoformat()} {video['id']}\n")
            
            print(f"Wrote {video['id']}");
            
        if found_existing:
            return video_ids

        # Get next page if it exists
        request = youtube.videos().list_next(request, response)
        #request = False

    return video_ids;

def find_log_tail(log_file, oldest_timestamp):
    lines = log_file.read_text().splitlines()
    for i, line in enumerate(reversed(lines)):
        timestamp = line.split()[0]
        if timestamp <= oldest_timestamp:
            return lines[-i:]
    return lines  # If no older timestamp found, return all lines


def archive_unliked_videos(unliked_ids, batch_time):
    archive_base = ROOT / "data/youtube/likes/archive"
    year = batch_time.year
    
    for video_id in unliked_ids:
        src_file = output_dir / f"{video_id}.json"
        if not src_file.exists():
            print(f"Warning: No active file for {video_id}")
            continue
            
        # Read and update data
        data = json.loads(src_file.read_text())
        data['unliked_at'] = batch_time.isoformat()
        
        # Ensure archive directory exists
        year_dir = archive_base / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        
        # Move to archive
        dest_file = year_dir / f"{video_id}.json"
        dest_file.write_text(json.dumps(data, indent=2))
        src_file.unlink()
        
        print(f"Archived {video_id}")

video_ids = retrieve_list()

oldest_like_id = video_ids[-1];
oldest_data_file =  output_dir / f"{oldest_like_id}.json"
oldest_data = json.loads(oldest_data_file.read_text())
oldest_timestamp = oldest_data['first_seen']

log_tail = find_log_tail(log_file, oldest_timestamp)
log_ids = [line.split()[1] for line in log_tail]

unlikes = set(log_ids) - set(video_ids)
new_unlikes = {
    video_id for video_id in unlikes
    if (output_dir / f"{video_id}.json").exists()
}

archive_unliked_videos(new_unlikes, batch_time);

##for line in reversed(list(log_file.open())):

print("Imported ", batch_time);
print("Save to", output_dir);
print(f"Oldest like at {oldest_timestamp}");
print("Done")
