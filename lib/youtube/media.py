import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from rate_limiter import RateLimiter
from rate_limits import YOUTUBE_MEDIA

import config
from util import dump_json

MEDIA_EXTENSIONS = {'.mp4', '.webm', '.mkv', '.m4a', '.opus', '.mp3', '.ogg', '.avi', '.mov', '.flv', '.wav', '.aac'}

FORMAT_ARGS = {
    'best': ['-f', 'bestvideo+bestaudio/best'],
    'audio': ['-f', 'bestaudio'],
}


class Media:

    @classmethod
    def download(cls, video_id, format='best'):
        # 1. Check existing pointer
        pointer = cls.get_pointer(video_id)
        if pointer:
            print(f'Found existing pointer: {pointer}')
            return pointer

        # 2. Scan configured media dir
        paths = cls._find_in_dir(config.MEDIA_DIR, video_id)
        if paths:
            print(f'Found in media dir: {paths[0]}')
            cls._save_all_pointers(video_id, paths, 'media_dir')
            return paths[0]

        # 3. locate by video ID
        paths = cls._locate(video_id, case_insensitive=False)
        if paths:
            print(f'Found via locate (id): {paths[0]}')
            cls._save_all_pointers(video_id, paths, 'locate_id')
            return paths[0]

        # 4. locate by title (if long enough)
        from youtube.video import Video
        video = Video.get(video_id)
        title = video.title
        if len(title) >= 10:
            sanitized = title.replace(' ', '_')
            paths = cls._locate(sanitized)
            if paths:
                print(f'Found via locate (title): {paths[0]}')
                cls._save_all_pointers(video_id, paths, 'locate_title')
                return paths[0]

        # 5. Download with yt-dlp
        print(f'Downloading {video_id} with yt-dlp...')
        path = cls._yt_dlp(video_id, config.MEDIA_DIR, format)
        if path:
            cls.save_pointer(video_id, path, format, 'yt-dlp')
            return path

        print(f'Failed to download {video_id}')
        return None

    @classmethod
    def get_pointer(cls, video_id, needs_video=False, needs_audio=False):
        from youtube.video import Video
        media_file = Video.get_active_dir(video_id) / 'media.json'
        if not media_file.exists():
            return None

        data = json.loads(media_file.read_text())
        for entry in data.get('files', []):
            if needs_video and not entry.get('has_video'):
                continue
            if needs_audio and not entry.get('has_audio'):
                continue
            path = Path(entry['path'])
            if path.exists():
                return path
        return None

    @classmethod
    def save_pointer(cls, video_id, path, format, found_via):
        from youtube.video import Video
        media_file = Video.get_active_dir(video_id) / 'media.json'

        if media_file.exists():
            data = json.loads(media_file.read_text())
        else:
            data = {'files': []}

        # Don't duplicate
        path_str = str(path)
        for entry in data['files']:
            if entry['path'] == path_str:
                return

        entry = {
            'path': path_str,
            'found_via': found_via,
            'added': datetime.now(timezone.utc).isoformat(),
        }
        if format:
            entry['format'] = format

        probe_data = cls.probe(path)
        if probe_data:
            entry.update(probe_data)

        data['files'].append(entry)
        dump_json(media_file, data)

    @classmethod
    def _save_all_pointers(cls, video_id, paths, found_via):
        """Save pointers for all paths, but only probe the first one."""
        cls.save_pointer(video_id, paths[0], None, found_via)
        for path in paths[1:]:
            cls._save_pointer_minimal(video_id, path, found_via)

    @classmethod
    def _save_pointer_minimal(cls, video_id, path, found_via):
        """Save a pointer without running ffprobe — deferred until needed."""
        from youtube.video import Video
        media_file = Video.get_active_dir(video_id) / 'media.json'

        if media_file.exists():
            data = json.loads(media_file.read_text())
        else:
            data = {'files': []}

        path_str = str(path)
        for entry in data['files']:
            if entry['path'] == path_str:
                return

        data['files'].append({
            'path': path_str,
            'found_via': found_via,
            'added': datetime.now(timezone.utc).isoformat(),
        })
        dump_json(media_file, data)

    @classmethod
    def probe(cls, path):
        data = cls._run_ffprobe(path)
        if not data:
            return None

        streams = data.get('streams', [])
        if not streams:
            return None

        video_stream = None
        audio_stream = None
        for s in streams:
            if s['codec_type'] == 'video' and not video_stream:
                video_stream = s
            elif s['codec_type'] == 'audio' and not audio_stream:
                audio_stream = s

        if not video_stream and not audio_stream:
            return None

        fmt = data.get('format', {})
        info = {
            'has_video': video_stream is not None,
            'has_audio': audio_stream is not None,
            'duration': float(fmt['duration']) if fmt.get('duration') else None,
            'size': int(fmt['size']) if fmt.get('size') else None,
        }

        if video_stream:
            info['video_codec'] = video_stream.get('codec_name')
            info['width'] = video_stream.get('width')
            info['height'] = video_stream.get('height')

        if audio_stream:
            info['audio_codec'] = audio_stream.get('codec_name')

        return info

    @classmethod
    def _run_ffprobe(cls, path):
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-print_format', 'json',
                 '-show_streams', '-show_format', str(path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return None
            return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            return None

    @classmethod
    def _find_in_dir(cls, directory, video_id):
        directory = Path(directory)
        if not directory.exists():
            return []
        results = []
        for path in directory.rglob(f'*{video_id}*'):
            if path.suffix.lower() in MEDIA_EXTENSIONS and path.is_file():
                results.append(path)
        return results

    @classmethod
    def _locate(cls, pattern, case_insensitive=True):
        cmd = ['locate', pattern]
        if case_insensitive:
            cmd = ['locate', '-i', pattern]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=30,
            )
            paths = []
            for line in result.stdout.strip().splitlines():
                p = Path(line)
                if p.suffix.lower() in MEDIA_EXTENSIONS:
                    paths.append(p)
            return paths
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    @classmethod
    def _yt_dlp(cls, video_id, dest_dir, format='best'):
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        format_args = FORMAT_ARGS.get(format, FORMAT_ARGS['best'])
        cmd = [
            'yt-dlp',
            *format_args,
            '--merge-output-format', 'mp4',
            '--output', str(dest_dir / '%(title)s [%(id)s].%(ext)s'),
            f'https://www.youtube.com/watch?v={video_id}',
        ]

        with RateLimiter.get().acquire(YOUTUBE_MEDIA):
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

        if result.returncode != 0:
            print(f'yt-dlp error: {result.stderr}')
            return None

        paths = cls._find_in_dir(dest_dir, video_id)
        return paths[0] if paths else None
