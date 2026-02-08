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
