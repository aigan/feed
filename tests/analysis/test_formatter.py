from types import SimpleNamespace
from unittest.mock import patch

import pytest

from analysis.yt_transcript_formatter import YTTranscriptFormatter

# ---------------------------------------------------------------------------
# merge_transcript_chunks
# ---------------------------------------------------------------------------

class TestMergeTranscriptChunks:
    def test_single_chunk(self):
        result = YTTranscriptFormatter.merge_transcript_chunks(["0: Hello world."])
        assert result == "0: Hello world."

    def test_two_chunks_trims_overlap_by_timestamp(self):
        chunk1 = "0: First sentence.\n50: Second sentence.\n100: Overlap start."
        chunk2 = "100: Overlap replaced.\n150: Third sentence."

        result = YTTranscriptFormatter.merge_transcript_chunks([chunk1, chunk2])
        lines = result.strip().split("\n")

        # chunk1 should be trimmed at timestamp 100
        assert "0: First sentence." in lines
        assert "50: Second sentence." in lines
        # The overlap line from chunk1 should NOT be present
        assert "100: Overlap start." not in lines
        # chunk2 content should be present
        assert "100: Overlap replaced." in lines
        assert "150: Third sentence." in lines

    def test_empty_returns_empty(self):
        result = YTTranscriptFormatter.merge_transcript_chunks([])
        assert result == ""


# ---------------------------------------------------------------------------
# extract_headings_with_timestamps
# ---------------------------------------------------------------------------

class TestExtractHeadingsWithTimestamps:
    def test_pairs_headings_with_following_timestamp(self):
        text = (
            "## Introduction\n"
            "0: Welcome to the video.\n"
            "30: Some more text.\n"
            "## Main Topic\n"
            "120: Now let's discuss.\n"
        )
        result = YTTranscriptFormatter.extract_headings_with_timestamps(text)
        assert len(result) == 2
        assert result[0] == (0, "Introduction")
        assert result[1] == (120, "Main Topic")


# ---------------------------------------------------------------------------
# insert_headings_in_transcript
# ---------------------------------------------------------------------------

class TestInsertHeadingsInTranscript:
    def test_headings_interleaved_at_correct_positions(self):
        transcript_text = "0: Hello.\n50: Middle.\n120: End."
        headings_text = "0 ## Introduction\n120 ## Conclusion"

        result = YTTranscriptFormatter.insert_headings_in_transcript(
            transcript_text, headings_text
        )
        lines = [l for l in result.strip().split("\n") if l.strip()]

        # Headings should appear before their timestamp's content line
        assert lines[0] == "## Introduction"
        assert lines[1] == "0: Hello."
        assert lines[2] == "50: Middle."
        assert lines[3] == "## Conclusion"
        assert lines[4] == "120: End."


# ---------------------------------------------------------------------------
# get_last_paragraphs
# ---------------------------------------------------------------------------

class TestGetLastParagraphs:
    def test_returns_last_n_timestamped_lines(self):
        text = (
            "## Some heading\n"
            "0: First paragraph.\n"
            "50: Second paragraph.\n"
            "100: Third paragraph.\n"
        )
        result = YTTranscriptFormatter.get_last_paragraphs(text, count=2)
        assert len(result) == 2
        assert result[0] == "50: Second paragraph."
        assert result[1] == "100: Third paragraph."


# ---------------------------------------------------------------------------
# merge_transcript_chunks  — edge cases
# ---------------------------------------------------------------------------

class TestMergeChunksEdgeCases:
    def test_chunk_without_timestamps_kept_entirely(self):
        chunk1 = "0: First sentence.\n50: Second sentence."
        chunk2 = "## A heading\nSome narrative text without timestamps."
        chunk3 = "100: Third sentence.\n150: Fourth sentence."

        result = YTTranscriptFormatter.merge_transcript_chunks([chunk1, chunk2, chunk3])
        assert "0: First sentence." in result
        assert "50: Second sentence." in result
        assert "## A heading" in result
        assert "Some narrative text without timestamps." in result
        assert "100: Third sentence." in result

    def test_three_chunks_overlap_correctly(self):
        chunk1 = "0: A.\n50: B.\n100: C."
        chunk2 = "100: C-replaced.\n150: D.\n200: E."
        chunk3 = "200: E-replaced.\n250: F."

        result = YTTranscriptFormatter.merge_transcript_chunks([chunk1, chunk2, chunk3])
        lines = result.strip().split("\n")

        assert "0: A." in lines
        assert "50: B." in lines
        assert "100: C." not in lines
        assert "100: C-replaced." in lines
        assert "150: D." in lines
        assert "200: E." not in lines
        assert "200: E-replaced." in lines
        assert "250: F." in lines

    def test_heading_lines_not_treated_as_timestamps(self):
        chunk1 = "0: First.\n50: Second.\n100: Third."
        chunk2 = "## Heading\n100: Third-replaced.\n150: Fourth."

        result = YTTranscriptFormatter.merge_transcript_chunks([chunk1, chunk2])
        lines = result.strip().split("\n")

        assert "## Heading" in lines
        assert "100: Third." not in lines
        assert "100: Third-replaced." in lines


# ---------------------------------------------------------------------------
# extract_first_timestamp  — edge cases
# ---------------------------------------------------------------------------

class TestExtractFirstTimestamp:
    def test_heading_only_returns_none(self):
        result = YTTranscriptFormatter.extract_first_timestamp("## Intro\n## Details")
        assert result is None

    def test_skips_heading_finds_content(self):
        result = YTTranscriptFormatter.extract_first_timestamp("## Intro\n42: Welcome.")
        assert result == 42

    def test_non_numeric_prefix_skipped(self):
        result = YTTranscriptFormatter.extract_first_timestamp("abc: Not.\n100: Real.")
        assert result == 100


# ---------------------------------------------------------------------------
# insert_headings_in_transcript  — edge cases
# ---------------------------------------------------------------------------

class TestInsertHeadingsEdgeCases:
    def test_empty_headings_text(self):
        transcript_text = "0: Hello.\n50: Middle.\n120: End."
        result = YTTranscriptFormatter.insert_headings_in_transcript(
            transcript_text, ""
        )
        lines = [l for l in result.strip().split("\n") if l.strip()]
        assert "0: Hello." in lines
        assert "50: Middle." in lines
        assert "120: End." in lines

    def test_empty_transcript_text(self):
        headings_text = "0 ## Introduction\n120 ## Conclusion"
        result = YTTranscriptFormatter.insert_headings_in_transcript(
            "", headings_text
        )
        lines = [l for l in result.strip().split("\n") if l.strip()]
        assert "## Introduction" in lines
        assert "## Conclusion" in lines


# ---------------------------------------------------------------------------
# get_last_paragraphs  — edge cases
# ---------------------------------------------------------------------------

class TestGetLastParagraphsEdgeCases:
    def test_no_timestamped_lines(self):
        text = "## Only headings\nSome prose without timestamps."
        result = YTTranscriptFormatter.get_last_paragraphs(text)
        assert result == []

    def test_fewer_than_count(self):
        text = "## Heading\n42: Only one paragraph."
        result = YTTranscriptFormatter.get_last_paragraphs(text, count=2)
        assert len(result) == 1
        assert result[0] == "42: Only one paragraph."


# ---------------------------------------------------------------------------
# YTTranscriptFormatter.get  — Result + force propagation
# ---------------------------------------------------------------------------

def _make_video(video_id="vid_test"):
    return SimpleNamespace(video_id=video_id, title="Test Video")


def _sample_transcript():
    return {
        "metadata": {"language_code": "en", "is_generated": True, "segment_count": 1, "video_id": "vid_test"},
        "segments": [{"start": 0.0, "duration": 1.0, "text": "hello"}],
    }


class TestFormatterGetResult:
    """YTTranscriptFormatter.get() returns a Result with text and did_work."""

    def test_cached_transcript_txt_returns_did_work_false(self, ctx, write_raw):
        write_raw("youtube/videos/active/vi/vid_test/processed/transcript.txt", "cached body")
        video = _make_video()
        result = YTTranscriptFormatter.get(video)
        assert result.text == "cached body"
        assert result.did_work is False

    def test_cached_marker_returns_empty_text_did_work_false(self, ctx, write_json):
        write_json("youtube/videos/active/vi/vid_test/transcript-unavailable.json",
                   {"reason": "TranscriptsDisabled", "checked_at": "2025-01-01"})
        video = _make_video()
        # Mimic Video.transcript() behaviour: marker exists → None
        video.transcript = lambda force=False: None
        result = YTTranscriptFormatter.get(video)
        assert result.text == ""
        assert result.did_work is False

    def test_fresh_unavailable_returns_empty_text_did_work_true(self, ctx):
        video = _make_video()
        # No marker on disk, video.transcript() returns None (fresh discovery
        # of unavailability — Video.transcript() will have just written the marker).
        # We simulate by patching transcript to return None *after* the marker
        # check has been performed by the formatter (which sees no marker).
        called = {"n": 0}

        def fake_transcript(force=False):
            # Simulate Video.transcript writing the marker as part of its work.
            from youtube import Video
            marker = Video.get_active_dir(video.video_id) / "transcript-unavailable.json"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text('{"reason": "x"}')
            called["n"] += 1
            return None

        video.transcript = fake_transcript
        result = YTTranscriptFormatter.get(video)
        assert result.text == ""
        assert result.did_work is True
        assert called["n"] == 1

    def test_newly_processed_returns_did_work_true(self, ctx, write_json):
        video = _make_video()
        write_json("youtube/videos/active/vi/vid_test/transcript.json", _sample_transcript())
        # Mock chunking + headings to avoid hitting an LLM.
        with patch.object(YTTranscriptFormatter, "get_chunk", side_effect=["0: hello\n", None]), \
             patch.object(YTTranscriptFormatter, "get_cleanup_headings", return_value=""):
            video.transcript = lambda force=False: _sample_transcript()
            result = YTTranscriptFormatter.get(video)
        assert result.did_work is True
        assert result.text  # non-empty
        out = ctx / "youtube/videos/active/vi/vid_test/processed/transcript.txt"
        assert out.exists()


class TestFormatterForcePropagation:
    """force=True must ignore caches at every level."""

    def test_get_force_ignores_cached_transcript_txt(self, ctx, write_raw):
        write_raw("youtube/videos/active/vi/vid_test/processed/transcript.txt", "old body")
        video = _make_video()
        video.transcript = lambda force=False: _sample_transcript()
        with patch.object(YTTranscriptFormatter, "get_chunk", side_effect=["0: new\n", None]) as mock_chunk, \
             patch.object(YTTranscriptFormatter, "get_cleanup_headings", return_value="") as mock_head:
            result = YTTranscriptFormatter.get(video, force=True)
        assert result.did_work is True
        assert "old body" not in result.text
        # force was forwarded to the inner caches
        mock_chunk.assert_called()
        for call in mock_chunk.call_args_list:
            assert call.kwargs.get("force") is True
        mock_head.assert_called_once()
        assert mock_head.call_args.kwargs.get("force") is True

    def test_get_force_passes_to_video_transcript(self, ctx):
        video = _make_video()
        captured = {}

        def fake_transcript(force=False):
            captured["force"] = force
            return _sample_transcript()

        video.transcript = fake_transcript
        with patch.object(YTTranscriptFormatter, "get_chunk", side_effect=["0: x\n", None]), \
             patch.object(YTTranscriptFormatter, "get_cleanup_headings", return_value=""):
            YTTranscriptFormatter.get(video, force=True)
        assert captured["force"] is True

    def test_get_chunk_force_false_uses_cache(self, ctx, write_raw):
        write_raw("youtube/videos/active/vi/vid_test/processed/transcript_chunks/000.txt", "cached chunk")
        video = _make_video()
        with patch.object(YTTranscriptFormatter, "run_chunk") as mock_run:
            text = YTTranscriptFormatter.get_chunk(video, _sample_transcript(), 0)
        assert text == "cached chunk"
        mock_run.assert_not_called()

    def test_get_chunk_force_true_ignores_cache(self, ctx, write_raw):
        write_raw("youtube/videos/active/vi/vid_test/processed/transcript_chunks/000.txt", "cached chunk")
        video = _make_video()
        with patch.object(YTTranscriptFormatter, "run_chunk", return_value="fresh chunk") as mock_run:
            text = YTTranscriptFormatter.get_chunk(video, _sample_transcript(), 0, force=True)
        assert text == "fresh chunk"
        mock_run.assert_called_once()

    def test_get_cleanup_headings_force_false_uses_cache(self, ctx, write_raw):
        write_raw("youtube/videos/active/vi/vid_test/processed/headings.txt", "cached headings")
        video = _make_video()
        with patch.object(YTTranscriptFormatter, "run_cleanup_headings") as mock_run:
            text = YTTranscriptFormatter.get_cleanup_headings(video, "transcript text")
        assert text == "cached headings"
        mock_run.assert_not_called()

    def test_get_cleanup_headings_force_true_ignores_cache(self, ctx, write_raw):
        write_raw("youtube/videos/active/vi/vid_test/processed/headings.txt", "cached headings")
        video = _make_video()
        with patch.object(YTTranscriptFormatter, "run_cleanup_headings", return_value="fresh headings") as mock_run:
            text = YTTranscriptFormatter.get_cleanup_headings(video, "transcript text", force=True)
        assert text == "fresh headings"
        mock_run.assert_called_once()
