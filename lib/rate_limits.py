from __future__ import annotations

# Per-bucket limits. Each bucket has a list of (window_seconds, max_cost)
# pairs. 'reset_timezone' is None for rolling windows, or a tz name for
# windows that reset at local midnight (YouTube Data API quota).
#
# When a new bucket is added without observational data, default to the
# upper end of what a heavy human user could plausibly do through the
# normal clients (website, TV, phone). See plan for rationale.

YOUTUBE_TIMEDTEXT = 'youtube.timedtext'
YOUTUBE_DATA_API = 'youtube.data_api_v3'
YOUTUBE_MEDIA = 'youtube.media'

BUCKETS = {
    YOUTUBE_TIMEDTEXT: {
        'windows': [
            (1, 1),
            (60, 5),
            (3600, 25),
            (86400, 200),
        ],
        'reset_timezone': None,
    },
    YOUTUBE_DATA_API: {
        'windows': [
            (86400, 10000),
        ],
        'reset_timezone': 'America/Los_Angeles',
    },
    YOUTUBE_MEDIA: {
        'windows': [
            (30, 1),
            (3600, 25),
            (86400, 150),
        ],
        'reset_timezone': None,
    },
}

# Documented per-call costs for YouTube Data API v3 operations we invoke.
# Costs that aren't listed default to 1 (the most common case).
# Reference: https://developers.google.com/youtube/v3/determine_quota_cost
DATA_API_COSTS = {
    'channels.list': 1,
    'playlists.list': 1,
    'playlistItems.list': 1,
    'videos.list': 1,
    'videos.getRating': 1,
    'subscriptions.list': 1,
    'search.list': 100,
}
