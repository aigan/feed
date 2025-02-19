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
    request = youtube.playlists().list(
        part="id",
        mine=True
    )

    return request.execute()
    
    
#    
#    video_ids = []
#    
#    while request:
#        response = request.execute()
#        found_existing = False
#        
#        for video in response['items']:
#            video_ids.append(video['id']);
#            output_file = output_dir / f"{video['id']}.json"
#        
#            if output_file.exists():
#                #print(f"Skipped {video['id']}");
#                found_existing = True
#                continue
#            
#            video_data = {
#                'first_seen': batch_time.isoformat(),
#                'video': video
#            }
#            
#            output_file.write_text(json.dumps(video_data, indent=2))
#            
#            with log_file.open('a') as f:
#                f.write(f"{batch_time.isoformat()} {video['id']}\n")
#            
#            print(f"Wrote {video['id']}");
#            
#        if found_existing:
#            return video_ids
#
#        # Get next page if it exists
#        request = youtube.videos().list_next(request, response)
#        #request = False
#
#    return video_ids;


video_ids = retrieve_list()

pprint(video_ids);

