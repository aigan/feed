#!/bin/env python
from youtube import Rating
from datetime import datetime, timezone

batch_time = datetime.now(timezone.utc)
ratings = Rating('like', batch_time)
ratings.update_likes()
