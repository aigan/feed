#!/bin/env python

from youtube import Video
from analysis import YTAPIVideoExtractor
from pprint import pprint

video_id = "pMFH1buJOKA" # Wayward Radio Ep. #3- The Grand RPG

video = Video.get(video_id)
print(f"Video {video_id} from {video.published_at}:\n{video.title}")

result = YTAPIVideoExtractor.get(video)

pprint(result)
