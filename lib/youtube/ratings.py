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
        self.output_dir = ROOT / f"data/youtube/{rating_type}s/active"
        self.log_file = ROOT / f"data/youtube/{rating_type}s/{rating_type}s.log"
        self.rating_type = rating_type

    def update(self):
        video_ids = self.retrieve_list()
        #print("Video ids");
        #pprint(video_ids)

        oldest_rating_id = video_ids[-1];
        oldest_data_file =  self.output_dir / f"{oldest_rating_id}.json"
        oldest_data = json.loads(oldest_data_file.read_text())
        oldest_timestamp = oldest_data['first_seen']
        #print(f"oldest rating id: {oldest_rating_id}")
        #print(f"oldest timestamp: {oldest_timestamp}")

        log_tail = self.find_log_tail(oldest_timestamp, len(video_ids))
        log_ids = [line.split()[1] for line in log_tail]
        #print("Log ids found")
        #pprint(log_ids)


        undoes = set(log_ids) - set(video_ids)
        new_undoes = {
            video_id for video_id in undoes
            if (self.output_dir / f"{video_id}.json").exists()
        }

        #print("undoes")
        #pprint(new_undoes)
        self.archive_undone_ratings(new_undoes)

        with self.log_file.open('a') as f:
            for video_id in reversed(video_ids):
                f.write(f"{self.batch_time.isoformat()} {video_id}\n")


    def retrieve_list(self):
        youtube = get_youtube_client()
        request = youtube.videos().list(
            part="id",
            myRating=self.rating_type,
            maxResults=10
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
                    'video': from_obj(item),
                }

                output_file.write_text(dump_json(data))
                print(f"Wrote {id}");

            if found_existing:
                return video_ids

            # Get next page if it exists
            request = youtube.videos().list_next(request, response)
            #request = False

        return video_ids;


    def find_log_tail(self, oldest_timestamp, offset):
        if not self.log_file.exists():
            return []
        lines = self.log_file.read_text().splitlines()
        for i, line in enumerate(list(reversed(lines))[offset:], start=offset):
            timestamp = line.split()[0]
            #print(f"Compare {timestamp} <= {oldest_timestamp} from line {line}")
            if timestamp <= oldest_timestamp:
                return lines[-i:]
        return lines  # If no older timestamp found, return all lines


    def archive_undone_ratings(self, unrated_ids):
        archive_base = ROOT / f"data/youtube/{self.rating_type}s/archive"
        year = self.batch_time.year
        year_dir = archive_base / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        for video_id in unrated_ids:
            src_file = self.output_dir / f"{video_id}.json"
            if not src_file.exists():
                print(f"Warning: No active file for {video_id}")
                continue

            # Read and update data
            data = json.loads(src_file.read_text())
            data['unliked_at'] = self.batch_time.isoformat()

            #print(f"Would archived {video_id}")

            # Move to archive
            dest_file = year_dir / f"{video_id}.json"
            dest_file.write_text(dump_json(data))
            src_file.unlink()

            print(f"Archived {video_id}")
