#!/bin/env python
from youtube import Subscription
from pprint import pprint

data = Subscription.get_all()
pprint(data)
