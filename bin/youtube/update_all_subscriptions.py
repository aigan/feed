#!/bin/env python
from youtube import get_youtube_client
from pprint import pprint
from datetime import datetime, timezone
from config import ROOT
from pathlib import Path
import json
from types import SimpleNamespace

batch_time = datetime.now(timezone.utc)
output_dir = ROOT / "data/youtube/subscriptions/active"
archive_dir = ROOT / "data/youtube/subscriptions/archive"

def to_obj(d):
    if isinstance(d, dict):
        return SimpleNamespace(**{k: to_obj(v) for k, v in d.items()})
    elif isinstance(d, list):
        return [to_obj(i) for i in d]
    return d


def retrieve_list():
    youtube = get_youtube_client()
    request = youtube.subscriptions().list(
        part="contentDetails,snippet",
        #forChannelId="UC_FfTzJh1Y4cIyjCj1xlUeQ",
        order="alphabetical",
        mine=True,
        maxResults=20
    )
    entry_ids = []
    
    while request:
        response = request.execute()
        #pprint(response);
        
        for item in to_obj(response['items']):
            id = item.snippet.resourceId.channelId
            entry_ids.append(id);
            output_file = output_dir / f"{id}.json"
        
            if output_file.exists():
                old_entry = json.loads(output_file.read_text())
                first_seen = old_entry['first_seen']
            else:
                first_seen = batch_time.isoformat(),
            
            entry = {
                'channel_id': id,
                'title': item.snippet.title,
                'subscription_id': item.id,
                'first_seen':  first_seen,
                'last_updated': batch_time.isoformat(),
                'activity_type': item.contentDetails.activityType,
                'new_item_count': item.contentDetails.newItemCount,
                'total_item_count': item.contentDetails.totalItemCount
            }
            
            output_file.write_text(json.dumps(entry, indent=2))
            print(f"Wrote {id}");
            
        #request = youtube.subscriptions().list_next(request, response)
        request = False

    return entry_ids;



#def archive_unliked_videos(unliked_ids, batch_time):
#     year = batch_time.year
#    
#    for video_id in unliked_ids:
#        src_file = output_dir / f"{video_id}.json"
#        if not src_file.exists():
#            print(f"Warning: No active file for {video_id}")
#            continue
#            
#        # Read and update data
#        data = json.loads(src_file.read_text())
#        data['unliked_at'] = batch_time.isoformat()
#        
#        # Ensure archive directory exists
#        year_dir = archive_base / str(year)
#        year_dir.mkdir(parents=True, exist_ok=True)
#        
#        # Move to archive
#        dest_file = year_dir / f"{video_id}.json"
#        dest_file.write_text(json.dumps(data, indent=2))
#        src_file.unlink()
#        
#        print(f"Archived {video_id}")

entry_ids = retrieve_list()

existing_files = list(output_dir.glob('*.json'))
existing_ids = {f.stem for f in existing_files}
unsubscribed = existing_ids - set(entry_ids)

pprint(unsubscribed);
print("Done")
