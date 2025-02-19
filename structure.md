youtube/
  videos/
    active/           # Current known videos
      ${video_id}/
        meta.json     # Current metadata with first_seen timestamp
    archive/          # Historical versions
      ${video_id}/
        ${timestamp}/ # Snapshot at point of change
  channels/
    active/
      ${channel_id}/
        meta.json
    archive/
      
      
youtube/
  interactions/
    likes/
      active/
      archive/
    dislikes/
      active/
      archive/
    subscriptions/    # Channels you subscribe to
      active/
      archive/
    playlists/
      ${playlist_id}/  # For each playlist you have
        active/        # Current videos in playlist
        archive/       # Videos removed from playlist
    watch_history/
      active/         # Recent watches
      archive/        # Older watch records
      
