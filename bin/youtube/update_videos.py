#!/bin/env python
from youtube import Subscription, Channel
from pprint import pprint
from itertools import islice

#from context import Context

#channel_id = "UCKW0bV5ltbfDuSw04N_vkyQ";
#channel = Channel.get(channel_id)

#for subscr in Subscription.get_all():
#    channel = subscr.channel
#    print(channel.title)

for subscr in islice(Subscription.get_hot(), 1):
    channel = subscr.channel
    print(channel.title)

print("done")


#subscr = next(data)
#pprint(subscr)

#channel = subscr.channel
#pprint(channel)

#context = Context.get()
#pprint(context.batch_time)
#Channel.update(channel.channel_id)
