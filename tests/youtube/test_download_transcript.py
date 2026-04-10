import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from youtube_transcript_api._errors import IpBlocked, RequestBlocked

sys.path.insert(0, 'bin/youtube')
from download_transcript import download_one, run_batch


def make_video(video_id, title='Test'):
    return SimpleNamespace(video_id=video_id, title=title)


class TestTranscriptDownloadPropagatesBlock:
    """IpBlocked from the youtube_transcript_api must propagate through Transcript.download."""

    @patch('youtube.transcript.YouTubeTranscriptApi')
    def test_block_from_list(self, mock_api_cls):
        """Block during transcript listing propagates."""
        from youtube.transcript import Transcript
        mock_api_cls.return_value.list.side_effect = IpBlocked('vid0')
        with pytest.raises((IpBlocked, RequestBlocked)):
            Transcript.download('vid0')

    @patch('youtube.transcript.YouTubeTranscriptApi')
    def test_block_from_fetch(self, mock_api_cls):
        """Block during transcript fetch propagates."""
        from youtube.transcript import Transcript
        mock_transcript = SimpleNamespace(
            language_code='en', language='English', is_generated=True,
            fetch=lambda: (_ for _ in ()).throw(IpBlocked('vid0')),
        )
        mock_api_cls.return_value.list.return_value = [mock_transcript]
        with pytest.raises((IpBlocked, RequestBlocked)):
            Transcript.download('vid0')


class TestDownloadOnePropagatesBlock:
    """IpBlocked from Transcript.download must propagate through download_one."""

    @patch('download_transcript.has_transcript', return_value=False)
    @patch('download_transcript.Transcript.download', side_effect=IpBlocked('vid0'))
    def test_ip_blocked_propagates(self, mock_dl, mock_has):
        video = make_video('vid0')
        with pytest.raises(IpBlocked):
            download_one(video)

    @patch('download_transcript.has_transcript', return_value=False)
    @patch('download_transcript.Transcript.download', side_effect=RequestBlocked('vid0'))
    def test_request_blocked_propagates(self, mock_dl, mock_has):
        video = make_video('vid0')
        with pytest.raises(RequestBlocked):
            download_one(video)


class TestRunBatchStopsOnBlock:
    """The batch must stop immediately when YouTube blocks requests."""

    def _videos(self):
        return [make_video(f'vid{i}') for i in range(5)]

    @patch('download_transcript.download_one')
    @patch('download_transcript.iterate_videos')
    def test_stops_on_ip_blocked(self, mock_iter, mock_dl):
        mock_iter.return_value = self._videos()
        mock_dl.side_effect = [
            'ok',
            IpBlocked('vid1'),
        ]

        downloaded, skipped, missing, errors = run_batch('PLabc')

        assert downloaded == 1
        assert mock_dl.call_count == 2

    @patch('download_transcript.download_one')
    @patch('download_transcript.iterate_videos')
    def test_stops_on_request_blocked(self, mock_iter, mock_dl):
        mock_iter.return_value = self._videos()
        mock_dl.side_effect = [
            'skip',
            'ok',
            RequestBlocked('vid2'),
        ]

        downloaded, skipped, missing, errors = run_batch('PLabc')

        assert downloaded == 1
        assert skipped == 1
        assert mock_dl.call_count == 3

    @patch('download_transcript.download_one')
    @patch('download_transcript.iterate_videos')
    def test_continues_on_normal_error(self, mock_iter, mock_dl):
        mock_iter.return_value = self._videos()
        mock_dl.side_effect = [
            'ok',
            RuntimeError('some error'),
            'ok',
            'skip',
            'ok',
        ]

        downloaded, skipped, missing, errors = run_batch('PLabc')

        assert downloaded == 3
        assert skipped == 1
        assert errors == 1
        assert mock_dl.call_count == 5

    @patch('download_transcript.download_one')
    @patch('download_transcript.iterate_videos')
    def test_no_processing_after_block(self, mock_iter, mock_dl):
        """After IpBlocked, no more videos should be touched at all."""
        call_log = []

        def side_effect(video, force=False):
            call_log.append(video.video_id)
            if video.video_id == 'vid1':
                raise IpBlocked('vid1')
            return 'ok'

        mock_iter.return_value = self._videos()
        mock_dl.side_effect = side_effect

        run_batch('PLabc')

        assert call_log == ['vid0', 'vid1']
