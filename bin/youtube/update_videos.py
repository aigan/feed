#!/bin/env python
from youtube import Subscription, Channel, Video
from pprint import pprint
from itertools import islice

#from context import Context

#channel_id = "UCKW0bV5ltbfDuSw04N_vkyQ" # jonas
#channel_id = "UCQeRaTukNYft1_6AZPACnog" # Asmon
#channel_id = "UC_FfTzJh1Y4cIyjCj1xlUeQ" # Welonz
#channel = Channel.get(channel_id)

#for subscr in Subscription.get_all():
#    channel = subscr.channel
#    print(channel.title)

#video_id = "wGEatMWM3oA" # from jonas
#video_id = "sSOxPJD-VNo" # fropm JRE
#video_id = "9dgHP3wrj8Q" # from AI and Games
#video_id = "r1WtK_6q2P4" # Upcoming PS event

#video = Video.get(video_id)
#print(f"Video {video_id} from {video.published_at}:\n{video.title}")

#print(f"\n\n## {channel.title}\n")
#for video in islice(channel.remote_uploads(), 1110):
#    print(f"Video {video.video_id} from {video.published_at}:\n{video.title}\n")



for subscr in islice(Subscription.get_hot(), 1):
    channel = subscr.channel
    print(f"\n\n## {channel.title}\n")
#    #for list in channel.playlists:
#    #    print(list.title)
    for video in islice(channel.remote_uploads(), 10000):
        print(f"Video {video.video_id} from {video.published_at}:\n{video.title}\n")



#subscr_list = Subscription.get_hot()
#subscr = next(subscr_list)
#channel = subscr.channel
#print(channel.title)

#for list in channel.playlists:
#    print(list.title)

print("done")


#subscr = next(data)
#pprint(subscr)

#channel = subscr.channel
#pprint(channel)

#context = Context.get()
#pprint(context.batch_time)
#Channel.update(channel.channel_id)
