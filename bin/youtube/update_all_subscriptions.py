#!/bin/env python
import youtube.client
youtube.client.API_RETRIES = 3

from youtube import Subscription

Subscription.update_all()
