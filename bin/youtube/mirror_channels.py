#!/bin/env python
from youtube import Channel, Subscription
from pprint import pprint
from itertools import islice
from context import Context

batch_time = Context.get().batch_time

for subscr in islice(Subscription.get_hot(), 2):
    channel = subscr.channel
    print(f"\n\n## {channel.title}: {channel.last_uploads_mirror}\n")
    if channel.last_uploads_mirror != None: continue

    #for video in channel.remote_uploads():
    #    print(f" * {video.published_at}: {video.title}")

    channel.last_uploads_mirror = batch_time
    #channel.save() # TODO

print("done")
