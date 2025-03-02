data/youtube/channels/
  active/
    CHANNEL_ID_1/
      channel.json
      playlists/
        PLAYLIST_ID_1.json
        uploads.json
      videos/
        VIDEO_ID_1.json
        VIDEO_ID_2.json
    CHANNEL_ID_2/
      ...
  archive/
    2024/
      week-01/
        CHANNEL_ID_1/
          channel.json  # Changed channel metadata
          playlists/
            PLAYLIST_ID_2.json  # Changed playlist
          videos/
            VIDEO_ID_3.json  # Changed video metadata
        CHANNEL_ID_2/
          videos/
            REMOVED_VIDEO_ID.json  # Removed video
      week-02/
        CHANNEL_ID_1/
          playlists/
            PLAYLIST_ID_1.json  # Changed playlist
    2023/
      ...
