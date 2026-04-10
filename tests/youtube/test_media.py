import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from youtube.media import Media

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_video_dir(ctx, video_id):
    d = ctx / f'youtube/videos/active/{video_id[:2]}/{video_id}'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_media_json(ctx, video_id, files):
    d = _make_video_dir(ctx, video_id)
    (d / 'media.json').write_text(json.dumps({'files': files}))


# ---------------------------------------------------------------------------
# get_pointer
# ---------------------------------------------------------------------------

class TestGetPointer:
    def test_returns_none_when_no_media_json(self, ctx):
        _make_video_dir(ctx, 'abc123xyz99')
        assert Media.get_pointer('abc123xyz99') is None

    def test_returns_path_when_file_exists(self, ctx, tmp_path):
        video_file = tmp_path / 'video.mp4'
        video_file.touch()
        _write_media_json(ctx, 'abc123xyz99', [
            {'path': str(video_file), 'has_video': True, 'has_audio': True},
        ])
        assert Media.get_pointer('abc123xyz99') == video_file

    def test_returns_none_when_file_missing_on_disk(self, ctx):
        _write_media_json(ctx, 'abc123xyz99', [
            {'path': '/nonexistent/video.mp4', 'has_video': True, 'has_audio': True},
        ])
        assert Media.get_pointer('abc123xyz99') is None

    def test_returns_first_match_when_no_filter(self, ctx, tmp_path):
        video_file = tmp_path / 'video.mp4'
        video_file.touch()
        _write_media_json(ctx, 'abc123xyz99', [
            {'path': str(video_file), 'has_video': True, 'has_audio': True},
        ])
        assert Media.get_pointer('abc123xyz99') == video_file


# ---------------------------------------------------------------------------
# save_pointer
# ---------------------------------------------------------------------------

class TestSavePointer:
    def test_creates_media_json(self, ctx):
        _make_video_dir(ctx, 'abc123xyz99')
        Media.save_pointer('abc123xyz99', Path('/srv/youtube/test.mp4'), 'best', 'yt-dlp')

        media_file = ctx / 'youtube/videos/active/ab/abc123xyz99/media.json'
        data = json.loads(media_file.read_text())
        assert len(data['files']) == 1
        assert data['files'][0]['path'] == '/srv/youtube/test.mp4'
        assert data['files'][0]['format'] == 'best'
        assert data['files'][0]['found_via'] == 'yt-dlp'

    def test_appends_to_existing(self, ctx, tmp_path):
        _write_media_json(ctx, 'abc123xyz99', [
            {'path': '/existing/video.mp4', 'format': 'best'},
        ])
        Media.save_pointer('abc123xyz99', Path('/new/audio.m4a'), 'audio', 'yt-dlp')

        media_file = ctx / 'youtube/videos/active/ab/abc123xyz99/media.json'
        data = json.loads(media_file.read_text())
        assert len(data['files']) == 2

    def test_no_duplicate(self, ctx):
        _make_video_dir(ctx, 'abc123xyz99')
        Media.save_pointer('abc123xyz99', Path('/srv/youtube/test.mp4'), 'best', 'yt-dlp')
        Media.save_pointer('abc123xyz99', Path('/srv/youtube/test.mp4'), 'best', 'yt-dlp')

        media_file = ctx / 'youtube/videos/active/ab/abc123xyz99/media.json'
        data = json.loads(media_file.read_text())
        assert len(data['files']) == 1


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------

PROBE_VIDEO_AUDIO = {
    'streams': [
        {'codec_type': 'audio', 'codec_name': 'aac', 'sample_rate': '44100', 'channels': 2},
        {'codec_type': 'video', 'codec_name': 'h264', 'width': 1920, 'height': 1080},
    ],
    'format': {'duration': '120.5', 'size': '5000000', 'format_name': 'mov,mp4'},
}

PROBE_AUDIO_ONLY = {
    'streams': [
        {'codec_type': 'audio', 'codec_name': 'opus', 'sample_rate': '48000', 'channels': 2},
    ],
    'format': {'duration': '300.0', 'size': '2000000', 'format_name': 'ogg'},
}

PROBE_NO_STREAMS = {
    'streams': [],
    'format': {'duration': '0', 'size': '100', 'format_name': 'unknown'},
}


class TestProbe:
    def test_video_and_audio(self, tmp_path):
        f = tmp_path / 'test.mp4'
        f.touch()
        with patch('youtube.media.Media._run_ffprobe', return_value=PROBE_VIDEO_AUDIO):
            info = Media.probe(f)
        assert info['has_video'] is True
        assert info['has_audio'] is True
        assert info['width'] == 1920
        assert info['height'] == 1080
        assert info['video_codec'] == 'h264'
        assert info['audio_codec'] == 'aac'
        assert info['duration'] == 120.5
        assert info['size'] == 5000000

    def test_audio_only(self, tmp_path):
        f = tmp_path / 'test.m4a'
        f.touch()
        with patch('youtube.media.Media._run_ffprobe', return_value=PROBE_AUDIO_ONLY):
            info = Media.probe(f)
        assert info['has_video'] is False
        assert info['has_audio'] is True
        assert info['audio_codec'] == 'opus'
        assert info.get('width') is None
        assert info.get('video_codec') is None

    def test_no_streams_returns_none(self, tmp_path):
        f = tmp_path / 'test.bin'
        f.touch()
        with patch('youtube.media.Media._run_ffprobe', return_value=PROBE_NO_STREAMS):
            assert Media.probe(f) is None

    def test_ffprobe_failure_returns_none(self, tmp_path):
        f = tmp_path / 'test.mp4'
        f.touch()
        with patch('youtube.media.Media._run_ffprobe', return_value=None):
            assert Media.probe(f) is None


# ---------------------------------------------------------------------------
# save_pointer with probe data
# ---------------------------------------------------------------------------

class TestSavePointerWithProbe:
    def test_stores_probe_data(self, ctx, tmp_path):
        _make_video_dir(ctx, 'abc123xyz99')
        f = tmp_path / 'test.mp4'
        f.touch()
        with patch.object(Media, 'probe', return_value={
            'has_video': True, 'has_audio': True,
            'width': 1920, 'height': 1080,
            'video_codec': 'h264', 'audio_codec': 'aac',
            'duration': 120.5, 'size': 5000000,
        }):
            Media.save_pointer('abc123xyz99', f, None, 'locate_id')

        media_file = ctx / 'youtube/videos/active/ab/abc123xyz99/media.json'
        data = json.loads(media_file.read_text())
        entry = data['files'][0]
        assert entry['has_video'] is True
        assert entry['has_audio'] is True
        assert entry['width'] == 1920

    def test_probe_failure_still_saves_pointer(self, ctx, tmp_path):
        _make_video_dir(ctx, 'abc123xyz99')
        f = tmp_path / 'test.mp4'
        f.touch()
        with patch.object(Media, 'probe', return_value=None):
            Media.save_pointer('abc123xyz99', f, None, 'locate_id')

        media_file = ctx / 'youtube/videos/active/ab/abc123xyz99/media.json'
        data = json.loads(media_file.read_text())
        assert len(data['files']) == 1
        assert 'has_video' not in data['files'][0]


# ---------------------------------------------------------------------------
# get_pointer filtering by has_video / has_audio
# ---------------------------------------------------------------------------

class TestGetPointerStreamFilter:
    def test_filter_video_only(self, ctx, tmp_path):
        audio_file = tmp_path / 'audio.m4a'
        audio_file.touch()
        video_file = tmp_path / 'video.mp4'
        video_file.touch()
        _write_media_json(ctx, 'abc123xyz99', [
            {'path': str(audio_file), 'has_video': False, 'has_audio': True},
            {'path': str(video_file), 'has_video': True, 'has_audio': True},
        ])
        assert Media.get_pointer('abc123xyz99', needs_video=True) == video_file

    def test_filter_audio_only(self, ctx, tmp_path):
        audio_file = tmp_path / 'audio.m4a'
        audio_file.touch()
        video_file = tmp_path / 'video.mp4'
        video_file.touch()
        _write_media_json(ctx, 'abc123xyz99', [
            {'path': str(audio_file), 'has_video': False, 'has_audio': True},
            {'path': str(video_file), 'has_video': True, 'has_audio': True},
        ])
        # Both have audio, so first match wins
        assert Media.get_pointer('abc123xyz99', needs_audio=True) == audio_file

    def test_no_filter_returns_first(self, ctx, tmp_path):
        audio_file = tmp_path / 'audio.m4a'
        audio_file.touch()
        _write_media_json(ctx, 'abc123xyz99', [
            {'path': str(audio_file), 'has_video': False, 'has_audio': True},
        ])
        assert Media.get_pointer('abc123xyz99') == audio_file


# ---------------------------------------------------------------------------
# _find_in_dir
# ---------------------------------------------------------------------------

class TestFindInDir:
    def test_finds_by_id_in_filename(self, tmp_path):
        video = tmp_path / 'Some Title [abc123xyz99].mp4'
        video.touch()
        with patch.object(Media, 'probe', return_value={'has_video': True, 'has_audio': True}):
            assert Media._find_in_dir(tmp_path, 'abc123xyz99') == [video]

    def test_finds_in_subdirectory(self, tmp_path):
        subdir = tmp_path / 'topic'
        subdir.mkdir()
        video = subdir / 'Title-abc123xyz99.mp4'
        video.touch()
        with patch.object(Media, 'probe', return_value={'has_video': True, 'has_audio': True}):
            assert Media._find_in_dir(tmp_path, 'abc123xyz99') == [video]

    def test_ignores_non_media_via_probe(self, tmp_path):
        (tmp_path / 'abc123xyz99.json').touch()
        (tmp_path / 'abc123xyz99.txt').touch()
        assert Media._find_in_dir(tmp_path, 'abc123xyz99') == []

    def test_returns_empty_for_missing_dir(self):
        assert Media._find_in_dir(Path('/nonexistent'), 'abc123') == []

    def test_returns_multiple_matches(self, tmp_path):
        f1 = tmp_path / 'Title-abc123xyz99.mp4'
        f2 = tmp_path / 'Title-abc123xyz99.m4a'
        f1.touch()
        f2.touch()
        with patch.object(Media, 'probe', return_value={'has_video': True, 'has_audio': True}):
            result = Media._find_in_dir(tmp_path, 'abc123xyz99')
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _locate
# ---------------------------------------------------------------------------

class TestLocate:
    def test_filters_to_media_extensions(self):
        stdout = '/srv/video/test-abc123.mp4\n/srv/docs/abc123.txt\n/srv/audio/abc123.m4a\n'
        result = MagicMock(stdout=stdout)
        with patch('subprocess.run', return_value=result):
            paths = Media._locate('abc123')
        assert paths == [Path('/srv/video/test-abc123.mp4'), Path('/srv/audio/abc123.m4a')]

    def test_returns_empty_on_no_matches(self):
        result = MagicMock(stdout='')
        with patch('subprocess.run', return_value=result):
            assert Media._locate('nonexistent') == []

    def test_returns_empty_on_timeout(self):
        import subprocess
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('locate', 30)):
            assert Media._locate('abc123') == []


# ---------------------------------------------------------------------------
# download (integration of the chain)
# ---------------------------------------------------------------------------

class TestDownload:
    def test_returns_from_pointer(self, ctx, tmp_path):
        video_file = tmp_path / 'video.mp4'
        video_file.touch()
        _make_video_dir(ctx, 'abc123xyz99')
        _write_media_json(ctx, 'abc123xyz99', [
            {'path': str(video_file), 'has_video': True, 'has_audio': True},
        ])
        result = Media.download('abc123xyz99')
        assert result == video_file

    def test_finds_in_media_dir_and_saves_pointer(self, ctx, tmp_path):
        _make_video_dir(ctx, 'abc123xyz99')
        video_file = tmp_path / 'Some Title [abc123xyz99].mp4'
        video_file.touch()

        probe_data = {'has_video': True, 'has_audio': True, 'width': 1920, 'height': 1080,
                      'video_codec': 'h264', 'audio_codec': 'aac', 'duration': 60.0, 'size': 1000}
        with patch('config.MEDIA_DIR', tmp_path), \
             patch.object(Media, 'probe', return_value=probe_data):
            result = Media.download('abc123xyz99')

        assert result == video_file
        media_file = ctx / 'youtube/videos/active/ab/abc123xyz99/media.json'
        data = json.loads(media_file.read_text())
        assert data['files'][0]['found_via'] == 'media_dir'
        assert data['files'][0]['has_video'] is True
        assert 'format' not in data['files'][0]

    def test_saves_all_found_files(self, ctx, tmp_path):
        _make_video_dir(ctx, 'abc123xyz99')
        video_file = tmp_path / 'Title [abc123xyz99].mp4'
        audio_file = tmp_path / 'Title [abc123xyz99].m4a'
        video_file.touch()
        audio_file.touch()

        def fake_probe(path):
            if path.suffix == '.mp4':
                return {'has_video': True, 'has_audio': True, 'width': 1920, 'height': 1080,
                        'video_codec': 'h264', 'audio_codec': 'aac', 'duration': 60.0, 'size': 5000}
            return {'has_video': False, 'has_audio': True,
                    'audio_codec': 'aac', 'duration': 60.0, 'size': 1000}

        with patch('config.MEDIA_DIR', tmp_path), \
             patch.object(Media, 'probe', side_effect=fake_probe):
            result = Media.download('abc123xyz99')

        media_file = ctx / 'youtube/videos/active/ab/abc123xyz99/media.json'
        data = json.loads(media_file.read_text())
        assert len(data['files']) == 2

    def test_falls_through_to_locate_by_id(self, ctx, tmp_path):
        _make_video_dir(ctx, 'abc123xyz99')

        locate_result = MagicMock(stdout='/srv/documentary/Test-abc123xyz99.mp4\n')
        with patch('config.MEDIA_DIR', tmp_path), \
             patch('subprocess.run', return_value=locate_result), \
             patch.object(Media, 'probe', return_value={'has_video': True, 'has_audio': True}):
            result = Media.download('abc123xyz99')

        assert result == Path('/srv/documentary/Test-abc123xyz99.mp4')

    def test_falls_through_to_locate_by_title(self, ctx, tmp_path):
        _make_video_dir(ctx, 'abc123xyz99')
        video_data = {
            'video_id': 'abc123xyz99', 'title': 'A Long Enough Title',
            'channel_id': 'ch1', 'published_at': '2024-01-01T00:00:00Z',
            'first_seen': '2024-01-01T00:00:00Z', 'last_updated': '2024-01-01T00:00:00Z',
            'description': '', 'thumbnails_data': {}, 'tags': [], 'category_id': 1,
            'live_status': 'none', 'duration_data': 'PT0S', 'spatial_dimension_type': '2d',
            'resolution_tier': 'hd', 'captioned': True, 'licensed_content': False,
            'content_rating_data': {}, 'viewing_projection': 'rectangular',
            'privacy_status': 'public', 'license': 'youtube', 'embeddable': True,
            'public_stats_viewable': True, 'made_for_kids': False,
            'view_count': 0, 'like_count': 0, 'comment_count': 0,
            'topic_details': {}, 'has_paid_product_placement': False,
        }
        video_dir = ctx / 'youtube/videos/active/ab/abc123xyz99'
        (video_dir / 'video.json').write_text(json.dumps(video_data))

        def fake_locate(cmd, **kwargs):
            pattern = cmd[-1]
            if 'A_Long_Enough_Title' in pattern:
                return MagicMock(stdout='/srv/docs/A_Long_Enough_Title.mp4\n')
            return MagicMock(stdout='')

        with patch('config.MEDIA_DIR', tmp_path), \
             patch('subprocess.run', side_effect=fake_locate), \
             patch.object(Media, 'probe', return_value={'has_video': True, 'has_audio': True}):
            result = Media.download('abc123xyz99')

        assert result == Path('/srv/docs/A_Long_Enough_Title.mp4')

    def test_short_title_skips_title_locate(self, ctx, tmp_path):
        _make_video_dir(ctx, 'abc123xyz99')
        video_data = {
            'video_id': 'abc123xyz99', 'title': 'Short',
            'channel_id': 'ch1', 'published_at': '2024-01-01T00:00:00Z',
            'first_seen': '2024-01-01T00:00:00Z', 'last_updated': '2024-01-01T00:00:00Z',
            'description': '', 'thumbnails_data': {}, 'tags': [], 'category_id': 1,
            'live_status': 'none', 'duration_data': 'PT0S', 'spatial_dimension_type': '2d',
            'resolution_tier': 'hd', 'captioned': True, 'licensed_content': False,
            'content_rating_data': {}, 'viewing_projection': 'rectangular',
            'privacy_status': 'public', 'license': 'youtube', 'embeddable': True,
            'public_stats_viewable': True, 'made_for_kids': False,
            'view_count': 0, 'like_count': 0, 'comment_count': 0,
            'topic_details': {}, 'has_paid_product_placement': False,
        }
        video_dir = ctx / 'youtube/videos/active/ab/abc123xyz99'
        (video_dir / 'video.json').write_text(json.dumps(video_data))

        locate_calls = []
        def fake_run(cmd, **kwargs):
            locate_calls.append(cmd)
            return MagicMock(stdout='', returncode=1)

        with patch('config.MEDIA_DIR', tmp_path), \
             patch('subprocess.run', side_effect=fake_run), \
             patch.object(Media, '_yt_dlp', return_value=None):
            Media.download('abc123xyz99')

        # Only one locate call (by ID), not by title
        assert len(locate_calls) == 1
