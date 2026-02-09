#!/bin/env python
import sys

from analysis import DescriptionFilter
from context import Context
from youtube import Subscription

batch_time = Context.get().batch_time

if len(sys.argv) > 1:
    channel_id = sys.argv[1]
    print(f"Indexing channel {channel_id}")
    DescriptionFilter.index_channel(channel_id)
else:
    for sub in Subscription.get_all():
        print(f"\n{sub.title} ({sub.channel_id})")
        DescriptionFilter.index_channel(sub.channel_id)

print("\nDone")
