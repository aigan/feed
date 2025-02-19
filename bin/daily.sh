#!/bin/bash
cd "$(dirname "$0")/.."  # Move to project root
eval "$(direnv export bash 2>/dev/null)"

exec &>> var/daily.log  # Redirect both stdout and stderr to log

echo "START: $(date -u -Iseconds)"

bin/youtube/update_likes.py
# Future:
# bin/youtube/get_playlists.py
# bin/mastodon/get_bookmarks.py

echo "DONE: $(date -u -Iseconds)"
