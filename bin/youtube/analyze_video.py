#!/bin/env python

from youtube import Video
from analysis import YTAPIVideoExtractor, YTTranscriptFormatter
from analysis.description_filter import DescriptionFilter
from pprint import pprint
import argparse

#video_id = "pMFH1buJOKA" # Wayward Radio Ep. #3- The Grand RPG
#video_id = "-rs7LHtODh4" # Half-Life 3 - The Rise, Fall & Rebirth
#video_id = "IGLGi5RK8V8" # Interview with the "Father of the Elder Scrolls" | Julian Jensen (aka Julian LeFay)
#video_id = "u7JFmo-vaXo" # Check Out: Chains of Freedom
#video_id = "vnOrkLQAU7E" # 13 Turns to Kill the Spawn God // CHAINS OF FREEDOM // Part 19
#video_id = "OkoHyOhHEuk" # TDS Celebrates Earth Day by Tackling Climate Change | The Daily Show
#video_id = "LPBI7WVD0zI" # Top U.S. & World Headlines — April 21, 2025

parser = argparse.ArgumentParser(description="Process a YouTube video.")
parser.add_argument("video_id", help="The YouTube video ID to process")
args = parser.parse_args()
video_id = args.video_id



video = Video.get(video_id)
print(f"Video {video_id} from {video.published_at}:\n{video.title}\nLength: {video.duration_formatted}")

channel = video.channel
print(f"Channel: {channel.title}")
print("Tags: " + ", ".join(video.tags))

print("\n*****\n")

print(video.description)

print("\n*****\n")

description = DescriptionFilter.get(video)
unique_len = DescriptionFilter.unique_length(video.description, video.channel_id)
print(description)
print(f"\nUnique length: {unique_len}")

#summary = YTAPIVideoExtractor.get(video)
#print("\n" + summary['text'] + "\n")

#result = YTTranscriptFormatter.get(video)
#print(result)

print("DONE")
