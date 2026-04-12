import sys
from types import SimpleNamespace
from unittest.mock import patch

from youtube_transcript_api._errors import IpBlocked, RequestBlocked

sys.path.insert(0, 'bin/youtube')
from fetch_transcripts import process_one, run_batch  # noqa: E402

from analysis.yt_transcript_formatter import Result  # noqa: E402


def make_video(video_id, title='Test'):
    return SimpleNamespace(video_id=video_id, title=title)


class TestProcessOneDelegatesToFormatter:
    """process_one calls get_transcript + get_headings and aggregates."""

    @patch('fetch_transcripts.YTTranscriptFormatter.get_headings')
    @patch('fetch_transcripts.YTTranscriptFormatter.get_transcript')
    def test_returns_aggregated_result(self, mock_tr, mock_hd):
        mock_tr.return_value = Result(text='body', did_work=True)
        mock_hd.return_value = Result(text='0 ## h', did_work=False)
        video = make_video('vid0')
        result = process_one(video)
        assert result.text == 'body'
        assert result.did_work is True  # tr.did_work OR hd.did_work
        mock_tr.assert_called_once_with(video, force=False)
        mock_hd.assert_called_once_with(video, force=False)

    @patch('fetch_transcripts.YTTranscriptFormatter.get_headings')
    @patch('fetch_transcripts.YTTranscriptFormatter.get_transcript')
    def test_passes_force_through_to_both(self, mock_tr, mock_hd):
        mock_tr.return_value = Result(text='body', did_work=True)
        mock_hd.return_value = Result(text='0 ## h', did_work=True)
        video = make_video('vid0')
        process_one(video, force=True)
        mock_tr.assert_called_once_with(video, force=True)
        mock_hd.assert_called_once_with(video, force=True)

    @patch('fetch_transcripts.YTTranscriptFormatter.get_headings')
    @patch('fetch_transcripts.YTTranscriptFormatter.get_transcript')
    def test_did_work_true_if_only_headings_ran(self, mock_tr, mock_hd):
        # Transcript cached, headings regenerated — overall did_work=True.
        mock_tr.return_value = Result(text='body', did_work=False)
        mock_hd.return_value = Result(text='0 ## h', did_work=True)
        result = process_one(make_video('vid0'))
        assert result.did_work is True

    @patch('fetch_transcripts.YTTranscriptFormatter.get_headings')
    @patch('fetch_transcripts.YTTranscriptFormatter.get_transcript')
    def test_did_work_false_if_both_cached(self, mock_tr, mock_hd):
        mock_tr.return_value = Result(text='body', did_work=False)
        mock_hd.return_value = Result(text='0 ## h', did_work=False)
        result = process_one(make_video('vid0'))
        assert result.did_work is False


class TestRunBatchCounters:
    """Counter behavior across the four outcomes."""

    def _videos(self, n=5):
        return [make_video(f'vid{i}') for i in range(n)]

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_counts_processed_cached_missing(self, mock_iter, mock_proc):
        mock_iter.return_value = self._videos(4)
        mock_proc.side_effect = [
            Result(text='a', did_work=True),   # processed
            Result(text='b', did_work=False),  # cached
            Result(text='', did_work=True),    # missing (fresh unavailable)
            Result(text='', did_work=False),   # missing (cached marker)
        ]
        processed, cached, missing, errors = run_batch('PLabc')
        assert processed == 1
        assert cached == 1
        assert missing == 2
        assert errors == 0

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_continues_on_normal_error(self, mock_iter, mock_proc):
        mock_iter.return_value = self._videos(4)
        mock_proc.side_effect = [
            Result(text='a', did_work=True),
            RuntimeError('boom'),
            Result(text='b', did_work=True),
            Result(text='c', did_work=False),
        ]
        processed, cached, missing, errors = run_batch('PLabc')
        assert processed == 2
        assert cached == 1
        assert errors == 1


class TestRunBatchStopsOnBlock:
    """IpBlocked / RequestBlocked from the formatter must stop the batch."""

    def _videos(self, n=5):
        return [make_video(f'vid{i}') for i in range(n)]

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_stops_on_ip_blocked(self, mock_iter, mock_proc):
        mock_iter.return_value = self._videos(5)
        mock_proc.side_effect = [
            Result(text='a', did_work=True),
            IpBlocked('vid1'),
        ]
        processed, cached, missing, errors = run_batch('PLabc')
        assert processed == 1
        assert mock_proc.call_count == 2

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_stops_on_request_blocked(self, mock_iter, mock_proc):
        mock_iter.return_value = self._videos(5)
        mock_proc.side_effect = [
            Result(text='c', did_work=False),
            Result(text='a', did_work=True),
            RequestBlocked('vid2'),
        ]
        processed, cached, missing, errors = run_batch('PLabc')
        assert processed == 1
        assert cached == 1
        assert mock_proc.call_count == 3

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_no_processing_after_block(self, mock_iter, mock_proc):
        call_log = []

        def side_effect(video, force=False):
            call_log.append(video.video_id)
            if video.video_id == 'vid1':
                raise IpBlocked('vid1')
            return Result(text='ok', did_work=True)

        mock_iter.return_value = self._videos(5)
        mock_proc.side_effect = side_effect
        run_batch('PLabc')
        assert call_log == ['vid0', 'vid1']


class TestRunBatchLimit:
    """--limit N counts videos where work was actually done; cached videos do not consume budget."""

    def _videos(self, n):
        return [make_video(f'vid{i}') for i in range(n)]

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_limit_one_stops_after_one_work_iteration(self, mock_iter, mock_proc):
        mock_iter.return_value = self._videos(5)
        mock_proc.side_effect = [
            Result(text='a', did_work=True),
        ]
        processed, cached, missing, errors = run_batch('PLabc', limit=1)
        assert processed == 1
        assert mock_proc.call_count == 1

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_limit_skips_past_cached_videos(self, mock_iter, mock_proc):
        """3 cached, then 1 work — limit=1 should walk past the cached and stop after the work."""
        mock_iter.return_value = self._videos(10)
        mock_proc.side_effect = [
            Result(text='c', did_work=False),
            Result(text='c', did_work=False),
            Result(text='c', did_work=False),
            Result(text='a', did_work=True),
            Result(text='extra', did_work=True),  # should NOT be reached
        ]
        processed, cached, missing, errors = run_batch('PLabc', limit=1)
        assert processed == 1
        assert cached == 3
        assert mock_proc.call_count == 4

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_limit_counts_fresh_missing_as_work(self, mock_iter, mock_proc):
        """Fresh unavailable discovery is work; cached marker is not."""
        mock_iter.return_value = self._videos(10)
        mock_proc.side_effect = [
            Result(text='', did_work=False),  # cached marker — free
            Result(text='', did_work=True),   # fresh unavailable — counts
            Result(text='extra', did_work=True),  # should NOT be reached
        ]
        processed, cached, missing, errors = run_batch('PLabc', limit=1)
        assert missing == 2
        assert mock_proc.call_count == 2

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_limit_counts_errors_as_work(self, mock_iter, mock_proc):
        """An attempted-and-failed video consumes the limit budget."""
        mock_iter.return_value = self._videos(10)
        mock_proc.side_effect = [
            RuntimeError('boom'),
            Result(text='extra', did_work=True),  # should NOT be reached
        ]
        processed, cached, missing, errors = run_batch('PLabc', limit=1)
        assert errors == 1
        assert mock_proc.call_count == 1

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_no_limit_processes_all(self, mock_iter, mock_proc):
        mock_iter.return_value = self._videos(3)
        mock_proc.side_effect = [
            Result(text='a', did_work=True),
            Result(text='b', did_work=True),
            Result(text='c', did_work=True),
        ]
        processed, cached, missing, errors = run_batch('PLabc')
        assert processed == 3


class TestRunBatchForceForwarded:
    """--force must reach process_one (and from there, the formatter)."""

    @patch('fetch_transcripts.process_one')
    @patch('fetch_transcripts.iterate_videos')
    def test_force_forwarded(self, mock_iter, mock_proc):
        mock_iter.return_value = [make_video('vid0')]
        mock_proc.return_value = Result(text='a', did_work=True)
        run_batch('PLabc', force=True)
        mock_proc.assert_called_once()
        # process_one(video, force=True)
        kwargs_force = mock_proc.call_args.kwargs.get('force')
        positional_force = (
            mock_proc.call_args.args[1] if len(mock_proc.call_args.args) >= 2 else None
        )
        assert kwargs_force is True or positional_force is True
