#!/bin/env python
import youtube.client
youtube.client.API_RETRIES = 3

from datetime import datetime, timezone

from youtube import Rating

batch_time = datetime.now(timezone.utc)
ratings = Rating('like', batch_time)
ratings.update()
