#!/bin/env python
from youtube import Subscription
from pprint import pprint

data = Subscription.get_all()
subscr = next(data)
pprint(subscr)

channel = subscr.channel
pprint(channel)
