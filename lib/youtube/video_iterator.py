import re

CHANNEL_RE = re.compile(r'^UC[a-zA-Z0-9_-]{22}$')
VIDEO_RE = re.compile(r'^[a-zA-Z0-9_-]{11}$')
PLAYLIST_PREFIXES = ('PL', 'UU', 'FL', 'OL', 'LL', 'WL', 'HL', 'RD', 'EL')


def detect_id_type(source_id: str) -> str:
    if CHANNEL_RE.match(source_id):
        return 'channel'
    if source_id.startswith(PLAYLIST_PREFIXES):
        return 'playlist'
    if VIDEO_RE.match(source_id):
        return 'video'
    return 'unknown'


def iterate_videos(source_id):
    from youtube import Channel, Playlist, Video

    id_type = detect_id_type(source_id)

    if id_type == 'video':
        return [Video.get(source_id)]

    if id_type == 'channel':
        return Channel.get(source_id).local_uploads()

    if id_type == 'playlist':
        _etag, video_ids = Playlist.retrieve_playlist_items(source_id)
        return (Video.get(video_id) for video_id in video_ids)

    raise ValueError(f'Cannot determine ID type for: {source_id}')
