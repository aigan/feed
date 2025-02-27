from youtube import get_youtube_client
from pprint import pprint
from datetime import datetime, timezone
from config import ROOT
from pathlib import Path
import json
from util import to_obj, from_obj, dump_json

class Rating:
    def __init__(self, rating_type: str, batch_time: datetime):
        self.batch_time = batch_time
        self.output_dir = ROOT / "data/youtube/likes/active"
        self.log_file = ROOT / "data/youtube/likes/likes.log"
        self.rating_type = rating_type

    def update_likes(self):
        video_ids = self.retrieve_list()

        oldest_like_id = video_ids[-1];
        oldest_data_file =  self.output_dir / f"{oldest_like_id}.json"
        oldest_data = json.loads(oldest_data_file.read_text())
        oldest_timestamp = oldest_data['first_seen']

        log_tail = self.find_log_tail(oldest_timestamp)
        log_ids = [line.split()[1] for line in log_tail]

        unlikes = set(log_ids) - set(video_ids)
        new_unlikes = {
            video_id for video_id in unlikes
            if (self.output_dir / f"{video_id}.json").exists()
        }

        self.archive_unliked_videos(new_unlikes, self.batch_time);
    

    def retrieve_list(self):
        youtube = get_youtube_client()
        request = youtube.videos().list(
            part="id",
            myRating="like",
            maxResults=50
        )
        video_ids = []
    
        while request:
            response = request.execute()
            found_existing = False

            for item in to_obj(response['items']):
                id = item.id
                video_ids.append(id)
                output_file = self.output_dir / f"{id}.json"

                if output_file.exists():
                    print(f"Skipped {id}");
                    found_existing = True
                    continue

                data = {
                    'first_seen': self.batch_time.isoformat(),
                    'video': form_obj(item), 
                }

                output_file.write_text(dump_json(data))

                with self.log_file.open('a') as f:
                    f.write(f"{self.batch_time.isoformat()} {id}\n")

                print(f"Wrote {id}");

            if found_existing:
                return video_ids

            # Get next page if it exists
            request = youtube.videos().list_next(request, response)
            #request = False

        return video_ids;


    def find_log_tail(self, oldest_timestamp):
        lines = self.log_file.read_text().splitlines()
        for i, line in enumerate(reversed(lines)):
            timestamp = line.split()[0]
            if timestamp <= oldest_timestamp:
                return lines[-i:]
        return lines  # If no older timestamp found, return all lines


    def archive_unliked_videos(self, unliked_ids, batch_time):
        archive_base = ROOT / "data/youtube/likes/archive"
        year = self.batch_time.year

        for video_id in unliked_ids:
            src_file = self.output_dir / f"{video_id}.json"
            if not src_file.exists():
                print(f"Warning: No active file for {video_id}")
                continue

            # Read and update data
            data = json.loads(src_file.read_text())
            data['unliked_at'] = self.batch_time.isoformat()

            # Ensure archive directory exists
            year_dir = archive_base / str(year)
            year_dir.mkdir(parents=True, exist_ok=True)

            # Move to archive
            dest_file = year_dir / f"{video_id}.json"
            dest_file.write_text(dump_json(data))
            src_file.unlink()

            print(f"Archived {video_id}")



##for line in reversed(list(log_file.open())):

#print("Imported ", batch_time);
#print("Save to", output_dir);
#print(f"Oldest like at {oldest_timestamp}");
#print("Done")
