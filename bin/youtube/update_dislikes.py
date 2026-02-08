#!/bin/env python
from datetime import datetime, timezone

from youtube import Rating

batch_time = datetime.now(timezone.utc)
ratings = Rating('dislike', batch_time)
ratings.update()
