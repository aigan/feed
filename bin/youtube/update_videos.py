#!/bin/env python
from youtube import Subscription, Channel
from pprint import pprint
from itertools import islice

#from context import Context

channel_id = "UCKW0bV5ltbfDuSw04N_vkyQ" # jonas
#channel_id = "UCQeRaTukNYft1_6AZPACnog" # Asmon
#channel_id = "UC_FfTzJh1Y4cIyjCj1xlUeQ" # Welonz
#channel = Channel.get(channel_id)

#for subscr in Subscription.get_all():
#    channel = subscr.channel
#    print(channel.title)


for subscr in islice(Subscription.get_hot(), 1):
    channel = subscr.channel
    print(f"\n\n## {channel.title}\n")
    #for list in channel.playlists:
    #    print(list.title)
    for (video_id, published_at) in islice(channel.get_uploads(), 3):
        print(f"video {video_id} at {published_at}")



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
