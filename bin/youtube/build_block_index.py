#!/bin/env python
import argparse
from itertools import islice

from analysis import DescriptionFilter
from context import Context
from youtube import Subscription

batch_time = Context.get().batch_time

parser = argparse.ArgumentParser(description='Build block index for channel descriptions.')
parser.add_argument('channel_id', nargs='?', help='Channel ID (optional; default: all subscriptions)')
parser.add_argument('--limit', type=int, default=None, help='Process at most N channels (default: no limit)')
args = parser.parse_args()

if args.channel_id:
    print(f"Indexing channel {args.channel_id}")
    DescriptionFilter.index_channel(args.channel_id)
else:
    for sub in islice(Subscription.get_all(), args.limit):
        print(f"\n{sub.title} ({sub.channel_id})")
        DescriptionFilter.index_channel(sub.channel_id)

print("\nDone")
