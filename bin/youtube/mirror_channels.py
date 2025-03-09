#!/bin/env python
from youtube import Channel, Subscription
from pprint import pprint
from itertools import islice

for subscr in islice(Subscription.get_hot(), 1):
    channel = subscr.channel
    print(f"\n\n## {channel.title}\n")
    local_uploads_count = channel.local_uploads_count()
    print(f"Local uploads: {local_uploads_count}")
    print(f"Channel uploads: {channel.video_count}")
    print(f"Tital items from subscr: {subscr.total_item_count}")


print("done")
