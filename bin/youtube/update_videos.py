#!/bin/env python
from youtube import Subscription, Channel, Video
from pprint import pprint
from itertools import islice

from context import Context
batch_time = Context.get().batch_time

print(f"Update video list. Batch {batch_time}\n")

#channel_id = "UCKW0bV5ltbfDuSw04N_vkyQ" # jonas
#channel_id = "UCQeRaTukNYft1_6AZPACnog" # Asmon
#channel_id = "UC_FfTzJh1Y4cIyjCj1xlUeQ" # Welonz
#channel_id = "UCY3A_5R_m3PXCn5XDhvBBsg" # Adam Millard
#channel_id = "UCXde0XwoBkAB8qvyPZBQstQ" # DON'T NOD
#channel_id = "UCZ7AeeVbyslLM_8-nVy2B8Q" # Skillup
#channel_id = "UCxvSr5kwfPwWBp9aTvyO2iw" # Belinda Ercan
#channel_id = "UCXlJYhNoCb7LH9M15GO26yA" # Jade Lore

#video_id = "wGEatMWM3oA" # from jonas
#video_id = "sSOxPJD-VNo" # fropm JRE
#video_id = "9dgHP3wrj8Q" # from AI and Games
#video_id = "r1WtK_6q2P4" # Upcoming PS event

#video = Video.get(video_id)
#print(f"Video {video_id} from {video.published_at}:\n{video.title}")

#print(f"\n\n## {channel.title}\n")
#for video in islice(channel.remote_uploads(), 1110):
#    print(f"Video {video.video_id} from {video.published_at}:\n{video.title}\n")


#for subscr in islice(Subscription.get_hot(), 3):
for subscr in Subscription.get_hot():
    channel = subscr.channel
    print(f"## {channel.title} - {channel.channel_id}")
    channel.mirror_uploads()
    print("\n")


#subscr_list = Subscription.get_hot()
#subscr = next(subscr_list)
#channel = subscr.channel
#print(channel.title)

#for list in channel.playlists:
#    print(list.title)

print("done")
