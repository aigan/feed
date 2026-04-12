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
        # ## heading lines are stripped from cleanup output — headings now
        # come from the separate full-transcript pass, not the chunk prompt.
        assert "## A heading" not in result
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

    def test_heading_lines_stripped_from_merged_output(self):
        # Old cached chunks from before the split still contain `## ...` lines.
        # merge_transcript_chunks must strip them so the cleaned transcript
        # stays heading-free.
        chunk1 = "0: First.\n50: Second.\n100: Third."
        chunk2 = "## Heading\n100: Third-replaced.\n150: Fourth."

        result = YTTranscriptFormatter.merge_transcript_chunks([chunk1, chunk2])
        lines = result.strip().split("\n")

        assert "## Heading" not in lines
        assert "100: Third." not in lines
        assert "100: Third-replaced." in lines
        assert "150: Fourth." in lines


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

def _make_video(video_id="vid_test", duration_seconds=1800):
    return SimpleNamespace(
        video_id=video_id,
        title="Test Video",
        duration_seconds=duration_seconds,
    )


def _sample_transcript():
    return {
        "metadata": {"language_code": "en", "is_generated": True, "segment_count": 1, "video_id": "vid_test"},
        "segments": [{"start": 0.0, "duration": 1.0, "text": "hello"}],
    }


class TestGetTranscriptResult:
    """YTTranscriptFormatter.get_transcript() — pass-1 cleanup getter."""

    def test_cached_transcript_txt_with_valid_stamp_short_circuits(self, ctx, write_raw, write_json):
        write_raw("youtube/videos/active/vi/vid_test/processed/transcript.txt", "cached body")
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"cleanup_prompt_version": YTTranscriptFormatter.CLEANUP_PROMPT_VERSION},
        )
        video = _make_video()
        with patch.object(
            YTTranscriptFormatter, "get_chunk", side_effect=[None]
        ) as mock_chunk:
            result = YTTranscriptFormatter.get_transcript(video)
        assert result.text == "cached body"
        assert result.did_work is False
        mock_chunk.assert_not_called()

    def test_cached_marker_returns_empty_text_did_work_false(self, ctx, write_json):
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"unavailable_reason": "TranscriptsDisabled", "checked_at": "2025-01-01"},
        )
        video = _make_video()
        video.transcript = lambda force=False: None
        result = YTTranscriptFormatter.get_transcript(video)
        assert result.text == ""
        assert result.did_work is False

    def test_fresh_unavailable_returns_empty_text_did_work_true(self, ctx):
        video = _make_video()
        called = {"n": 0}

        def fake_transcript(force=False):
            from youtube import TranscriptMeta, Video
            meta = TranscriptMeta(Video.get_active_dir(video.video_id))
            meta.mark_unavailable("x")
            called["n"] += 1
            return None

        video.transcript = fake_transcript
        result = YTTranscriptFormatter.get_transcript(video)
        assert result.text == ""
        assert result.did_work is True
        assert called["n"] == 1

    def test_newly_processed_returns_did_work_true(self, ctx, write_json):
        video = _make_video()
        write_json("youtube/videos/active/vi/vid_test/transcript.json", _sample_transcript())
        with patch.object(YTTranscriptFormatter, "get_chunk", side_effect=["0: hello\n", None]):
            video.transcript = lambda force=False: _sample_transcript()
            result = YTTranscriptFormatter.get_transcript(video)
        assert result.did_work is True
        assert "0: hello" in result.text
        out = ctx / "youtube/videos/active/vi/vid_test/processed/transcript.txt"
        assert out.exists()

    def test_force_ignores_cached_transcript_and_propagates_to_chunks(self, ctx, write_raw, write_json):
        write_raw("youtube/videos/active/vi/vid_test/processed/transcript.txt", "old body")
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"cleanup_prompt_version": YTTranscriptFormatter.CLEANUP_PROMPT_VERSION},
        )
        video = _make_video()
        video.transcript = lambda force=False: _sample_transcript()
        with patch.object(
            YTTranscriptFormatter, "get_chunk", side_effect=["0: new\n", None]
        ) as mock_chunk:
            result = YTTranscriptFormatter.get_transcript(video, force=True)
        assert result.did_work is True
        assert "old body" not in result.text
        mock_chunk.assert_called()
        for call in mock_chunk.call_args_list:
            assert call.kwargs.get("force") is True

    def test_force_passes_to_video_transcript(self, ctx):
        video = _make_video()
        captured = {}

        def fake_transcript(force=False):
            captured["force"] = force
            return _sample_transcript()

        video.transcript = fake_transcript
        with patch.object(YTTranscriptFormatter, "get_chunk", side_effect=["0: x\n", None]):
            YTTranscriptFormatter.get_transcript(video, force=True)
        assert captured["force"] is True


class TestGetHeadingsResult:
    """YTTranscriptFormatter.get_headings() — pass-2 headings getter."""

    def test_cached_headings_with_valid_stamp_short_circuits(self, ctx, write_raw, write_json):
        write_raw("youtube/videos/active/vi/vid_test/processed/headings.txt", "0 ## Cached")
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {
                "headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION,
                "reconcile_prompt_version": YTTranscriptFormatter.RECONCILE_PROMPT_VERSION,
            },
        )
        video = _make_video()
        with patch.object(YTTranscriptFormatter, "run_cleanup_headings") as mock_run, \
             patch.object(YTTranscriptFormatter, "get_transcript") as mock_tr:
            result = YTTranscriptFormatter.get_headings(video)
        assert result.text == "0 ## Cached"
        assert result.did_work is False
        mock_run.assert_not_called()
        mock_tr.assert_not_called()

    def test_missing_reconcile_version_triggers_regeneration(self, ctx, write_raw, write_json):
        # Existing caches written before the reconciliation pass existed
        # have no `reconcile_prompt_version` and must be regenerated.
        write_raw("youtube/videos/active/vi/vid_test/processed/headings.txt", "stale")
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION},
        )
        video = _make_video()
        from analysis.yt_transcript_formatter import Result
        with patch.object(
            YTTranscriptFormatter, "get_transcript",
            return_value=Result(text="0: t", did_work=False),
        ), patch.object(
            YTTranscriptFormatter, "run_cleanup_headings", return_value="0 ## Fresh"
        ) as mock_run:
            result = YTTranscriptFormatter.get_headings(video)
        assert "Fresh" in result.text
        mock_run.assert_called_once()

    def test_missing_headings_triggers_regeneration(self, ctx, write_raw):
        # Deleting headings.txt must cause get_headings to regenerate it,
        # even if transcript.txt is cached.
        write_raw("youtube/videos/active/vi/vid_test/processed/transcript.txt", "0: cached")
        video = _make_video()
        with patch.object(
            YTTranscriptFormatter,
            "get_transcript",
            return_value=__import__("analysis.yt_transcript_formatter", fromlist=["Result"]).Result(text="0: cached", did_work=False),
        ), patch.object(
            YTTranscriptFormatter, "run_cleanup_headings", return_value="0 ## Fresh"
        ) as mock_run:
            result = YTTranscriptFormatter.get_headings(video)
        assert result.text == "0 ## Fresh"
        assert result.did_work is True
        mock_run.assert_called_once()

    def test_force_triggers_regeneration(self, ctx, write_raw, write_json):
        write_raw("youtube/videos/active/vi/vid_test/processed/headings.txt", "stale")
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION},
        )
        video = _make_video()
        from analysis.yt_transcript_formatter import Result
        with patch.object(
            YTTranscriptFormatter, "get_transcript",
            return_value=Result(text="0: t", did_work=False),
        ), patch.object(
            YTTranscriptFormatter, "run_cleanup_headings", return_value="0 ## Fresh"
        ) as mock_run:
            result = YTTranscriptFormatter.get_headings(video, force=True)
        assert result.text == "0 ## Fresh"
        mock_run.assert_called_once()

    def test_version_mismatch_triggers_regeneration(self, ctx, write_raw, write_json):
        write_raw("youtube/videos/active/vi/vid_test/processed/headings.txt", "stale")
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION - 1},
        )
        video = _make_video()
        from analysis.yt_transcript_formatter import Result
        with patch.object(
            YTTranscriptFormatter, "get_transcript",
            return_value=Result(text="0: t", did_work=False),
        ), patch.object(
            YTTranscriptFormatter, "run_cleanup_headings", return_value="0 ## Fresh"
        ) as mock_run:
            result = YTTranscriptFormatter.get_headings(video)
        assert "Fresh" in result.text
        mock_run.assert_called_once()

    def test_empty_transcript_skips_llm_pass(self, ctx):
        video = _make_video()
        from analysis.yt_transcript_formatter import Result
        with patch.object(
            YTTranscriptFormatter, "get_transcript",
            return_value=Result(text="", did_work=False),
        ), patch.object(
            YTTranscriptFormatter, "run_cleanup_headings"
        ) as mock_run:
            result = YTTranscriptFormatter.get_headings(video)
        assert result.text == ""
        assert result.did_work is False
        mock_run.assert_not_called()


class TestGetChunkCaching:
    """run_chunk file-level caching — unchanged by the refactor."""

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


# ---------------------------------------------------------------------------
# Prompt shape — guardrails against regressing the two-phase split
# ---------------------------------------------------------------------------

class TestCleanupPromptHeadingFree:
    def test_cleanup_prompt_has_no_heading_instructions(self):
        prompt = YTTranscriptFormatter.CLEANUP_PROMPT
        assert '##' not in prompt
        assert 'chapter heading' not in prompt.lower()
        assert 'heading' not in prompt.lower()

    def test_cleanup_prompt_still_does_prose_work(self):
        prompt = YTTranscriptFormatter.CLEANUP_PROMPT
        low = prompt.lower()
        assert 'paragraph' in low
        assert 'timestamp' in low or '{transcript_chunk}' in prompt

    def test_headings_prompt_template_has_placeholders(self):
        prompt = YTTranscriptFormatter.HEADINGS_PROMPT
        assert '{level_instructions}' in prompt
        assert '{example_output}' in prompt
        assert '{transcript}' in prompt


# ---------------------------------------------------------------------------
# build_headings_prompt — duration-aware level instructions
# ---------------------------------------------------------------------------

def _heading_levels(prompt: str):
    """Return the set of heading tokens that appear in actual example heading
    lines (a digit timestamp followed by a #-prefix). This deliberately
    ignores prose mentions like "do not use `####`" inside the instructions."""
    import re as _re
    return set(_re.findall(r'^\s*\d+\s+(#{1,6})\s', prompt, _re.MULTILINE))


class TestBuildHeadingsPrompt:
    def test_short_video_only_level_2(self):
        prompt = YTTranscriptFormatter.build_headings_prompt(300)
        levels = _heading_levels(prompt)
        assert '##' in levels
        assert '###' not in levels
        assert '####' not in levels
        assert '{transcript}' in prompt

    def test_short_boundary_at_cutoff(self):
        prompt = YTTranscriptFormatter.build_headings_prompt(
            YTTranscriptFormatter.HEADINGS_SHORT_CUTOFF
        )
        levels = _heading_levels(prompt)
        assert '##' in levels
        assert '###' not in levels
        assert '####' not in levels

    def test_medium_video_levels_2_and_3(self):
        prompt = YTTranscriptFormatter.build_headings_prompt(1800)
        levels = _heading_levels(prompt)
        assert '##' in levels
        assert '###' in levels
        assert '####' not in levels

    def test_medium_boundary_at_cutoff(self):
        prompt = YTTranscriptFormatter.build_headings_prompt(
            YTTranscriptFormatter.HEADINGS_MEDIUM_CUTOFF
        )
        levels = _heading_levels(prompt)
        assert '##' in levels
        assert '###' in levels
        assert '####' not in levels

    def test_long_video_levels_2_3_4(self):
        prompt = YTTranscriptFormatter.build_headings_prompt(5400)
        levels = _heading_levels(prompt)
        assert '##' in levels
        assert '###' in levels
        assert '####' in levels
        # Semantic relabeling locked in.
        low = prompt.lower()
        assert 'section' in low
        assert 'chapter' in low
        assert 'subtopic' in low

    def test_very_long_video_still_long_bucket(self):
        prompt = YTTranscriptFormatter.build_headings_prompt(20000)
        levels = _heading_levels(prompt)
        assert '####' in levels

    def test_missing_duration_falls_back_to_medium(self):
        for value in (0, None):
            prompt = YTTranscriptFormatter.build_headings_prompt(value)
            levels = _heading_levels(prompt)
            assert '##' in levels
            assert '###' in levels
            assert '####' not in levels


# ---------------------------------------------------------------------------
# get_transcript — cleanup pass caching + version invalidation
# ---------------------------------------------------------------------------

class TestGetTranscriptCaching:
    def test_runs_chunks_and_stamps_meta(self, ctx):
        video = _make_video()
        video.transcript = lambda force=False: _sample_transcript()
        with patch.object(
            YTTranscriptFormatter,
            "get_chunk",
            side_effect=["0: hello\n", None],
        ):
            result = YTTranscriptFormatter.get_transcript(video)
        assert "0: hello" in result.text
        assert result.did_work is True
        path = ctx / "youtube/videos/active/vi/vid_test/processed/transcript.txt"
        assert path.exists()
        assert path.read_text() == result.text
        import json as _json
        meta = _json.loads(
            (ctx / "youtube/videos/active/vi/vid_test/transcript-meta.json").read_text()
        )
        assert meta["cleanup_prompt_version"] == YTTranscriptFormatter.CLEANUP_PROMPT_VERSION
        assert "cleanup_updated_at" in meta

    def test_version_mismatch_triggers_regeneration(self, ctx, write_raw, write_json):
        write_raw(
            "youtube/videos/active/vi/vid_test/processed/transcript.txt",
            "stale",
        )
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"cleanup_prompt_version": YTTranscriptFormatter.CLEANUP_PROMPT_VERSION - 1},
        )
        video = _make_video()
        video.transcript = lambda force=False: _sample_transcript()
        with patch.object(
            YTTranscriptFormatter,
            "get_chunk",
            side_effect=["0: fresh\n", None],
        ) as mock_chunk:
            result = YTTranscriptFormatter.get_transcript(video)
        assert "fresh" in result.text
        assert "stale" not in result.text
        for call in mock_chunk.call_args_list:
            assert call.kwargs.get("force") is True

    def test_missing_stamp_treated_as_mismatch(self, ctx, write_raw):
        # Legacy cache with no meta file → regenerate.
        write_raw(
            "youtube/videos/active/vi/vid_test/processed/transcript.txt",
            "legacy",
        )
        video = _make_video()
        video.transcript = lambda force=False: _sample_transcript()
        with patch.object(
            YTTranscriptFormatter,
            "get_chunk",
            side_effect=["0: regenerated\n", None],
        ):
            result = YTTranscriptFormatter.get_transcript(video)
        assert "regenerated" in result.text
        assert "legacy" not in result.text


# ---------------------------------------------------------------------------
# parse_headings / format_headings — tuple ↔ text roundtrip
# ---------------------------------------------------------------------------

class TestParseAndFormatHeadings:
    def test_parse_level_two_and_three(self):
        text = "0 ## Intro\n300 ## Main\n450 ### Sub"
        result = YTTranscriptFormatter.parse_headings(text)
        assert result == [
            (0, 2, "Intro"),
            (300, 2, "Main"),
            (450, 3, "Sub"),
        ]

    def test_parse_recognizes_full_markdown_range(self):
        text = (
            "0 # Title\n"
            "60 ## Section\n"
            "120 ### Chapter\n"
            "180 #### Subtopic\n"
            "240 ##### Deeper\n"
            "300 ###### Deepest\n"
        )
        result = YTTranscriptFormatter.parse_headings(text)
        assert result == [
            (0, 1, "Title"),
            (60, 2, "Section"),
            (120, 3, "Chapter"),
            (180, 4, "Subtopic"),
            (240, 5, "Deeper"),
            (300, 6, "Deepest"),
        ]

    def test_parse_ignores_blank_and_commentary(self):
        text = "\n0 ## Intro\nrandom commentary\n300 ## Main\n"
        result = YTTranscriptFormatter.parse_headings(text)
        assert result == [(0, 2, "Intro"), (300, 2, "Main")]

    def test_format_headings_roundtrip(self):
        headings = [
            (0, 2, "Intro"),
            (300, 2, "Main"),
            (450, 3, "Sub"),
            (600, 4, "Subtopic"),
        ]
        text = YTTranscriptFormatter.format_headings(headings)
        assert text == "0 ## Intro\n300 ## Main\n450 ### Sub\n600 #### Subtopic"
        assert YTTranscriptFormatter.parse_headings(text) == headings


# ---------------------------------------------------------------------------
# post_hoc_merge — deterministic combining of LLM + manual chapters
# ---------------------------------------------------------------------------

class TestPostHocMerge:
    def test_no_manual_chapters_passes_llm_through(self):
        llm = [(0, 2, "Intro"), (300, 2, "Main")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, [])
        assert merged == llm
        assert unmatched == []

    def test_manual_inside_snap_window_replaces_title_at_llm_timestamp(self):
        llm = [(0, 2, "LLM Intro"), (305, 2, "LLM Main")]
        manual = [(300, "Manual Main")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        # Title swapped, LLM timestamp and level kept (transcript-accurate).
        assert (305, 2, "Manual Main") in merged
        assert (0, 2, "LLM Intro") in merged
        assert len(merged) == 2
        assert unmatched == []

    def test_manual_outside_snap_window_returned_unmatched(self):
        llm = [(0, 2, "Intro"), (500, 2, "Other")]
        manual = [(200, "Standalone")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        # Merge does not insert it deterministically — reconciliation handles it.
        assert merged == llm
        assert unmatched == [(200, "Standalone")]

    def test_preserves_llm_subheadings(self):
        llm = [(0, 2, "Main"), (100, 3, "Sub"), (500, 2, "Next")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, [])
        assert (100, 3, "Sub") in merged
        assert unmatched == []

    def test_manual_snaps_to_subheading_keeping_its_level(self):
        # The user's reported case: a level-2 manual chapter near only a
        # level-3 LLM heading must absorb into the subheading rather than
        # appear as a separate near-duplicate.
        llm = [(0, 2, "Top"), (300, 3, "Sub"), (600, 2, "Next")]
        manual = [(305, "Manual chapter")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        # The ### entry is replaced by the manual title, level kept at 3.
        assert (300, 3, "Manual chapter") in merged
        # No duplicate manual entry.
        assert len(merged) == 3
        assert unmatched == []

    def test_prefers_higher_level_when_multiple_in_window(self):
        # An LLM ## (15s away) and an LLM ### (3s away) are both within
        # window — the ## wins because highest level (lowest number) takes
        # precedence over distance.
        llm = [(285, 2, "Section"), (303, 3, "Subsection")]
        manual = [(300, "Manual")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        assert (285, 2, "Manual") in merged
        assert (303, 3, "Subsection") in merged
        assert unmatched == []

    def test_ties_broken_by_distance(self):
        # Same level on both sides — closest one wins.
        llm = [(290, 2, "A"), (315, 2, "B")]
        manual = [(305, "Manual")]
        merged, _ = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        # 315 is 10s away vs 290 at 15s — 315 wins.
        assert (315, 2, "Manual") in merged
        assert (290, 2, "A") in merged

    def test_two_manuals_cannot_consume_same_llm_heading(self):
        # Both manual chapters are within window of the same LLM heading.
        # First takes it; second has no other candidate → unmatched.
        llm = [(300, 2, "LLM")]
        manual = [(295, "First"), (310, "Second")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        assert (300, 2, "First") in merged
        assert unmatched == [(310, "Second")]

    def test_result_sorted_by_timestamp(self):
        llm = [(500, 2, "Late"), (100, 2, "Early")]
        manual = [(105, "Middle")]
        merged, _ = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        offsets = [off for off, _, _ in merged]
        assert offsets == sorted(offsets)

    def test_facade_example_collapses_near_duplicates(self):
        # Real inputs from POv1cOX8xUM that originally produced
        # near-duplicate `## A Behaviour Language` + `### ABL ...` pairs.
        # With cross-level snap, the manual chapters merge into the LLM
        # subheadings without inserting duplicates.
        manual = [
            (0,    'Introduction'),
            (88,   'About Facade'),
            (516,  'The Design of Facade'),
            (739,  'The Drama Manager'),
            (1068, 'A Behaviour Language'),
            (1350, 'Reading Keyboard Input'),
            (1549, 'Closing'),
        ]
        llm = [
            (35,   2, 'Facade introduction and what makes it unique'),
            (282,  2, 'The origins of Facade and how it was developed'),
            (454,  2, 'How Facade works under the hood'),
            (518,  3, 'Social games: affinity and therapy'),
            (679,  3, 'The Drama Manager and beat sequencing'),
            (1073, 3, 'ABL and coordinated character behaviour'),
            (1352, 3, 'Natural language processing and player input'),
            (1554, 2, "Facade's legacy and the lack of a sequel"),
            (1669, 2, 'Outro and acknowledgements'),
        ]

        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        by_off = {off: (lvl, title) for off, lvl, title in merged}

        # Bookend rule: `Introduction` at 0 is anchored to 0:00 even
        # though no LLM heading sits within SNAP_WINDOW. It absorbs the
        # default `##` level.
        assert by_off[0] == (2, 'Introduction')

        # Near-duplicate pairs collapse into single entries at the LLM
        # timestamp, with the LLM heading's level preserved.
        assert by_off[518]  == (3, 'The Design of Facade')
        assert by_off[1073] == (3, 'A Behaviour Language')
        assert by_off[1352] == (3, 'Reading Keyboard Input')
        # `Closing` (1549) snaps to LLM 1554 (5s away, level 2).
        assert by_off[1554] == (2, 'Closing')

        # Manual chapters with no LLM heading inside SNAP_WINDOW go to
        # `unmatched` for the LLM reconciliation pass.
        assert unmatched == [
            (88,  'About Facade'),       # closest LLM at 35s — 53s drift
            (739, 'The Drama Manager'),  # closest LLM at 679s — 60s drift
        ]

        offsets = [off for off, _, _ in merged]
        assert offsets == sorted(offsets)


class TestPostHocMergeBookends:
    def test_manual_at_zero_anchors_to_start_with_no_nearby_llm(self):
        # No LLM heading near 0 → prepend a new `##` entry at 0.
        llm = [(120, 2, "First topic"), (500, 2, "Second")]
        manual = [(0, "Introduction")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        assert merged[0] == (0, 2, "Introduction")
        assert (120, 2, "First topic") in merged
        assert (500, 2, "Second") in merged
        assert unmatched == []

    def test_manual_at_zero_absorbs_nearby_llm_at_zero_offset(self):
        # An LLM heading already at 0 — absorb its level, swap title.
        llm = [(0, 2, "Some intro"), (300, 2, "Other")]
        manual = [(0, "Introduction")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        assert (0, 2, "Introduction") in merged
        assert (300, 2, "Other") in merged
        assert len(merged) == 2
        assert unmatched == []

    def test_manual_at_zero_absorbs_nearby_llm_offset_kept_at_zero(self):
        # An LLM heading at 25s within window — its level transfers to
        # the bookend, but the offset is forced to 0 (the user's
        # explicit requirement: first timestamp must remain 00:00).
        llm = [(25, 2, "LLM intro"), (300, 2, "Main")]
        manual = [(0, "Introduction")]
        merged, _ = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        # The LLM 25s entry was consumed, replaced by a 0s entry.
        assert merged[0] == (0, 2, "Introduction")
        assert all(off != 25 for off, _, _ in merged)
        assert (300, 2, "Main") in merged

    def test_manual_near_end_snaps_to_duration(self):
        # A manual chapter 5s before the video end snaps onto the
        # duration timestamp, absorbing the closest LLM heading's level.
        llm = [(0, 2, "Start"), (1690, 3, "Late chapter")]
        manual = [(1695, "Outro")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(
            llm, manual, duration_seconds=1700
        )
        assert (1700, 3, "Outro") in merged
        assert all(off != 1690 for off, _, _ in merged)
        assert (0, 2, "Start") in merged
        assert unmatched == []

    def test_manual_outside_end_window_treated_normally(self):
        # 100s from the end is well outside SNAP_WINDOW — the chapter
        # follows the standard snap path.
        llm = [(0, 2, "Start"), (1600, 2, "Section"), (1700, 2, "End")]
        manual = [(1605, "Closing")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(
            llm, manual, duration_seconds=1700
        )
        # Standard snap: closest level-2 within window is 1600.
        assert (1600, 2, "Closing") in merged
        # The actual end LLM heading is untouched.
        assert (1700, 2, "End") in merged
        assert unmatched == []

    def test_no_duration_disables_end_bookend(self):
        # When duration_seconds is None, end-bookend logic does not fire.
        llm = [(0, 2, "Start"), (1600, 2, "Final LLM")]
        manual = [(1700, "Outro")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(llm, manual)
        # 1700 is 100s from 1600 — outside window, unmatched.
        assert (1600, 2, "Final LLM") in merged
        assert unmatched == [(1700, "Outro")]

    def test_llm_only_first_heading_pulled_to_zero(self):
        # No manual chapters at all — the LLM's first heading sits at 5s
        # and should be anchored to 0:00 (the v2UUjnDBMg4 case).
        llm = [(5, 2, "Why X"), (81, 2, "Other"), (151, 2, "Last")]
        merged, unmatched = YTTranscriptFormatter.post_hoc_merge(
            llm, [], duration_seconds=200
        )
        assert merged[0] == (0, 2, "Why X")
        assert (81, 2, "Other") in merged
        assert unmatched == []

    def test_llm_only_last_heading_pushed_to_duration(self):
        # Last LLM heading is exactly SNAP_WINDOW seconds before the end
        # (30s of 181) — the boundary case from v2UUjnDBMg4.
        llm = [(0, 2, "Start"), (81, 2, "Mid"), (151, 2, "Last")]
        merged, _ = YTTranscriptFormatter.post_hoc_merge(
            llm, [], duration_seconds=181
        )
        assert (181, 2, "Last") in merged
        assert all(off != 151 for off, _, _ in merged)

    def test_llm_first_heading_outside_window_not_anchored(self):
        # First heading at 60s — too far from 0 to be anchored.
        llm = [(60, 2, "Late start"), (300, 2, "Other")]
        merged, _ = YTTranscriptFormatter.post_hoc_merge(
            llm, [], duration_seconds=600
        )
        assert merged[0] == (60, 2, "Late start")

    def test_llm_last_heading_outside_window_not_anchored(self):
        # Last heading is 100s before the end — outside SNAP_WINDOW.
        llm = [(0, 2, "Start"), (500, 2, "Other")]
        merged, _ = YTTranscriptFormatter.post_hoc_merge(
            llm, [], duration_seconds=600
        )
        assert merged[-1] == (500, 2, "Other")

    def test_single_heading_only_anchors_start_not_end(self):
        # A lone heading should not be pushed to the end of a tiny video.
        llm = [(5, 2, "Only")]
        merged, _ = YTTranscriptFormatter.post_hoc_merge(
            llm, [], duration_seconds=30
        )
        assert merged == [(0, 2, "Only")]


# ---------------------------------------------------------------------------
# run_cleanup_headings — end-to-end wiring of the headings phase
# ---------------------------------------------------------------------------

class TestRunCleanupHeadings:
    def test_calls_llm_with_transcript_and_writes_headings_file(self, ctx):
        video = _make_video()
        transcript_text = "0: First paragraph.\n300: Second paragraph."
        llm_response = "0 ## Intro\n300 ## Main"

        with patch.object(YTTranscriptFormatter, "ask_llm", return_value=llm_response) as mock_llm, \
             patch("analysis.YTAPIVideoExtractor.get_description_timestamps", return_value=[]):
            result = YTTranscriptFormatter.run_cleanup_headings(video, transcript_text)

        mock_llm.assert_called_once()
        assert "0 ## Intro" in result
        assert "300 ## Main" in result
        path = ctx / "youtube/videos/active/vi/vid_test/processed/headings.txt"
        assert path.exists()
        assert path.read_text() == result + "\n"
        # Raw LLM output is also persisted now, with a trailing newline.
        llm_path = ctx / "youtube/videos/active/vi/vid_test/processed/headings_llm.txt"
        assert llm_path.exists()
        assert llm_path.read_text() == "0 ## Intro\n300 ## Main\n"
        # Headings phase stamps both step versions and update timestamps.
        import json as _json
        meta = _json.loads((ctx / "youtube/videos/active/vi/vid_test/transcript-meta.json").read_text())
        assert meta["headings_prompt_version"] == YTTranscriptFormatter.HEADINGS_PROMPT_VERSION
        assert "headings_updated_at" in meta
        assert meta["llm_headings_prompt_version"] == YTTranscriptFormatter.HEADINGS_PROMPT_VERSION
        assert "llm_headings_updated_at" in meta

    def test_manual_chapters_merged_into_output(self, ctx):
        video = _make_video()
        transcript_text = "0: First.\n305: Second."
        llm_response = "0 ## LLM Intro\n305 ## LLM Main"

        with patch.object(YTTranscriptFormatter, "ask_llm", return_value=llm_response), \
             patch("analysis.YTAPIVideoExtractor.get_description_timestamps", return_value=[(300, "Manual Main")]):
            result = YTTranscriptFormatter.run_cleanup_headings(video, transcript_text)

        # Manual title should snap to LLM timestamp inside the window.
        assert "305 ## Manual Main" in result
        assert "LLM Main" not in result

    def test_unmatched_manual_triggers_llm_reconciliation(self, ctx):
        # Manual chapter at 200s with no LLM heading inside SNAP_WINDOW
        # — must dispatch a second `ask_llm` call (the reconciliation pass)
        # whose response replaces the merged list.
        video = _make_video()
        transcript_text = "0: First.\n500: Second."
        llm_headings_response = "0 ## LLM Intro\n500 ## LLM Other"
        reconciled_response = (
            "0 ## LLM Intro\n200 ## Standalone\n500 ## LLM Other"
        )

        with patch.object(
            YTTranscriptFormatter,
            "ask_llm",
            side_effect=[llm_headings_response, reconciled_response],
        ) as mock_llm, patch(
            "analysis.YTAPIVideoExtractor.get_description_timestamps",
            return_value=[(200, "Standalone")],
        ):
            result = YTTranscriptFormatter.run_cleanup_headings(video, transcript_text)

        # Two LLM calls: one for headings, one for reconciliation.
        assert mock_llm.call_count == 2
        reconcile_call = mock_llm.call_args_list[1]
        assert reconcile_call.args[0] is YTTranscriptFormatter.RECONCILE_PROMPT
        params = reconcile_call.args[1]
        assert "200 Standalone" in params["unmatched"]
        assert "0 ## LLM Intro" in params["merged"]

        # Final headings.txt is the reconciliation response.
        assert "200 ## Standalone" in result
        path = ctx / "youtube/videos/active/vi/vid_test/processed/headings.txt"
        assert path.read_text() == result + "\n"

    def test_no_unmatched_skips_reconciliation_call(self, ctx):
        # Sanity guard: when every manual chapter snaps deterministically,
        # the reconciliation call must not fire (only the headings LLM call).
        video = _make_video()
        transcript_text = "0: First.\n305: Second."
        llm_response = "0 ## LLM Intro\n305 ## LLM Main"

        with patch.object(
            YTTranscriptFormatter, "ask_llm", return_value=llm_response,
        ) as mock_llm, patch(
            "analysis.YTAPIVideoExtractor.get_description_timestamps",
            return_value=[(300, "Manual Main")],
        ):
            YTTranscriptFormatter.run_cleanup_headings(video, transcript_text)

        # One call for headings, no reconciliation.
        assert mock_llm.call_count == 1


class TestReconcileWithLlm:
    def test_formats_inputs_and_parses_response(self):
        merged = [(0, 2, "Intro"), (500, 2, "Outro")]
        unmatched = [(200, "New chapter")]
        response = "0 ## Intro\n200 ## New chapter\n500 ## Outro"

        with patch.object(
            YTTranscriptFormatter, "ask_llm", return_value=response,
        ) as mock_llm:
            result = YTTranscriptFormatter.reconcile_with_llm(merged, unmatched)

        mock_llm.assert_called_once()
        args, kwargs = mock_llm.call_args
        assert args[0] is YTTranscriptFormatter.RECONCILE_PROMPT
        params = args[1]
        assert params["merged"] == "0 ## Intro\n500 ## Outro"
        assert params["unmatched"] == "200 New chapter"
        assert kwargs["profile"] == "headings"
        assert result == [
            (0, 2, "Intro"),
            (200, 2, "New chapter"),
            (500, 2, "Outro"),
        ]


class TestGetLlmHeadingsCaching:
    """get_llm_headings() — file-level caching of the raw LLM table of contents."""

    def test_cached_file_with_valid_stamp_skips_llm(self, ctx, write_raw, write_json):
        write_raw(
            "youtube/videos/active/vi/vid_test/processed/headings_llm.txt",
            "0 ## Cached\n300 ## Main",
        )
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"llm_headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION},
        )
        video = _make_video()
        with patch.object(YTTranscriptFormatter, "run_headings") as mock_run:
            result = YTTranscriptFormatter.get_llm_headings(video, "0: transcript body")
        mock_run.assert_not_called()
        assert result == [(0, 2, "Cached"), (300, 2, "Main")]

    def test_missing_file_calls_llm_and_writes_cache(self, ctx):
        video = _make_video()
        with patch.object(
            YTTranscriptFormatter,
            "run_headings",
            return_value=[(0, 2, "Fresh"), (500, 3, "Sub")],
        ) as mock_run:
            result = YTTranscriptFormatter.get_llm_headings(video, "0: body")
        mock_run.assert_called_once()
        assert result == [(0, 2, "Fresh"), (500, 3, "Sub")]
        path = ctx / "youtube/videos/active/vi/vid_test/processed/headings_llm.txt"
        assert path.exists()
        assert path.read_text() == "0 ## Fresh\n500 ### Sub\n"
        import json as _json
        meta = _json.loads(
            (ctx / "youtube/videos/active/vi/vid_test/transcript-meta.json").read_text()
        )
        assert meta["llm_headings_prompt_version"] == YTTranscriptFormatter.HEADINGS_PROMPT_VERSION
        assert "llm_headings_updated_at" in meta

    def test_force_ignores_cache(self, ctx, write_raw, write_json):
        write_raw(
            "youtube/videos/active/vi/vid_test/processed/headings_llm.txt",
            "0 ## Stale",
        )
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"llm_headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION},
        )
        video = _make_video()
        with patch.object(
            YTTranscriptFormatter, "run_headings", return_value=[(0, 2, "Fresh")]
        ) as mock_run:
            result = YTTranscriptFormatter.get_llm_headings(video, "0: body", force=True)
        mock_run.assert_called_once()
        assert result == [(0, 2, "Fresh")]
        path = ctx / "youtube/videos/active/vi/vid_test/processed/headings_llm.txt"
        assert path.read_text() == "0 ## Fresh\n"

    def test_version_mismatch_triggers_regeneration(self, ctx, write_raw, write_json):
        write_raw(
            "youtube/videos/active/vi/vid_test/processed/headings_llm.txt",
            "0 ## Old",
        )
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"llm_headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION - 1},
        )
        video = _make_video()
        with patch.object(
            YTTranscriptFormatter, "run_headings", return_value=[(0, 2, "Fresh")]
        ) as mock_run:
            YTTranscriptFormatter.get_llm_headings(video, "0: body")
        mock_run.assert_called_once()

    def test_run_cleanup_headings_reuses_cached_llm_output(self, ctx, write_raw, write_json):
        """With headings_llm.txt already on disk, the merge runs without an LLM call."""
        write_raw(
            "youtube/videos/active/vi/vid_test/processed/headings_llm.txt",
            "0 ## LLM Intro\n305 ## LLM Main",
        )
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {"llm_headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION},
        )
        video = _make_video()
        transcript_text = "0: First.\n305: Second."
        with patch.object(YTTranscriptFormatter, "ask_llm") as mock_llm, \
             patch("analysis.YTAPIVideoExtractor.get_description_timestamps", return_value=[(300, "Manual Main")]):
            result = YTTranscriptFormatter.run_cleanup_headings(video, transcript_text)
        mock_llm.assert_not_called()
        assert "305 ## Manual Main" in result
        # And the merged result is also persisted (with a trailing newline).
        path = ctx / "youtube/videos/active/vi/vid_test/processed/headings.txt"
        assert path.exists()
        assert path.read_text() == result + "\n"

    def test_get_headings_force_reuses_cached_llm_file(self, ctx, write_raw, write_json):
        # `get_headings(force=True)` invalidates its own output (headings.txt)
        # but must not re-run the LLM step — headings_llm.txt is an
        # independent dependency with its own cache.
        write_raw(
            "youtube/videos/active/vi/vid_test/processed/headings_llm.txt",
            "0 ## Cached LLM\n305 ## Cached Main",
        )
        write_raw(
            "youtube/videos/active/vi/vid_test/processed/headings.txt",
            "0 ## Stale Merged",
        )
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {
                "llm_headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION,
                "headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION,
            },
        )
        write_raw(
            "youtube/videos/active/vi/vid_test/processed/transcript.txt",
            "0: body\n305: more",
        )
        write_json(
            "youtube/videos/active/vi/vid_test/transcript-meta.json",
            {
                "llm_headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION,
                "headings_prompt_version": YTTranscriptFormatter.HEADINGS_PROMPT_VERSION,
                "cleanup_prompt_version": YTTranscriptFormatter.CLEANUP_PROMPT_VERSION,
            },
        )
        video = _make_video()
        with patch.object(YTTranscriptFormatter, "ask_llm") as mock_llm, \
             patch(
                 "analysis.YTAPIVideoExtractor.get_description_timestamps",
                 return_value=[(300, "Manual Main")],
             ):
            result = YTTranscriptFormatter.get_headings(video, force=True)
        mock_llm.assert_not_called()
        llm_path = ctx / "youtube/videos/active/vi/vid_test/processed/headings_llm.txt"
        merged_path = ctx / "youtube/videos/active/vi/vid_test/processed/headings.txt"
        # Raw LLM file is untouched.
        assert llm_path.read_text() == "0 ## Cached LLM\n305 ## Cached Main"
        # Merged file was rebuilt from the cached LLM headings + manual chapters.
        assert "305 ## Manual Main" in result.text
        assert "Stale Merged" not in merged_path.read_text()


# ---------------------------------------------------------------------------
# get_transcript_with_headers — on-demand merge iterator
# ---------------------------------------------------------------------------

class TestGetTranscriptWithHeaders:
    def test_yields_interleaved_lines(self, ctx):
        from analysis.yt_transcript_formatter import Result
        video = _make_video()
        transcript_text = "0: Hello.\n50: Middle.\n120: End."
        headings_text = "0 ## Introduction\n120 ## Conclusion"
        with patch.object(
            YTTranscriptFormatter, "get_transcript",
            return_value=Result(text=transcript_text, did_work=False),
        ), patch.object(
            YTTranscriptFormatter, "get_headings",
            return_value=Result(text=headings_text, did_work=False),
        ):
            lines = list(YTTranscriptFormatter.get_transcript_with_headers(video))
        assert lines == [
            "## Introduction",
            "0: Hello.",
            "50: Middle.",
            "## Conclusion",
            "120: End.",
        ]

    def test_empty_transcript_yields_nothing(self, ctx):
        from analysis.yt_transcript_formatter import Result
        video = _make_video()
        with patch.object(
            YTTranscriptFormatter, "get_transcript",
            return_value=Result(text="", did_work=False),
        ), patch.object(
            YTTranscriptFormatter, "get_headings"
        ) as mock_head:
            lines = list(YTTranscriptFormatter.get_transcript_with_headers(video))
        assert lines == []
        # get_headings should not even be called when there's no transcript.
        mock_head.assert_not_called()
