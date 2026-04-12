from youtube.transcript import Transcript


class TestProcessTimestamps:
    def test_mmss_format(self):
        text = "0:00 Introduction\n1:30 Chapter one"
        result = Transcript.process_timestamps(text)
        assert result == "[ts 0] 0:00 Introduction\n[ts 90] 1:30 Chapter one"

    def test_hmmss_format(self):
        text = "1:02:30 Long chapter"
        result = Transcript.process_timestamps(text)
        assert result == "[ts 3750] 1:02:30 Long chapter"

    def test_non_timestamp_lines_preserved(self):
        text = "Hello world\nThis is not a timestamp\n2:00 But this is"
        result = Transcript.process_timestamps(text)
        assert "Hello world" in result
        assert "This is not a timestamp" in result
        assert "[ts 120] 2:00 But this is" in result

    def test_mixed_content(self):
        text = (
            "Video chapters:\n"
            "0:00 Intro\n"
            "Some description text\n"
            "5:30 Main topic\n"
            "1:00:00 Conclusion"
        )
        result = Transcript.process_timestamps(text)
        lines = result.split("\n")
        assert lines[0] == "Video chapters:"
        assert lines[1] == "[ts 0] 0:00 Intro"
        assert lines[2] == "Some description text"
        assert lines[3] == "[ts 330] 5:30 Main topic"
        assert lines[4] == "[ts 3600] 1:00:00 Conclusion"

    def test_empty_string(self):
        assert Transcript.process_timestamps("") == ""

    def test_no_timestamps(self):
        text = "Just a regular description\nWith multiple lines"
        assert Transcript.process_timestamps(text) == text

    def test_dash_separator_is_stripped(self):
        # Non-alphanumeric separators between the timestamp and the title
        # are consumed by the pattern.
        text = "3:45 - Some topic"
        result = Transcript.process_timestamps(text)
        assert result == "[ts 225] 3:45 Some topic"

    def test_bracketed_mmss_format(self):
        text = "[00:00] Introduction\n[01:28] About Facade"
        result = Transcript.process_timestamps(text)
        assert result == "[ts 0] 00:00 Introduction\n[ts 88] 01:28 About Facade"

    def test_bracketed_hmmss_format(self):
        text = "[1:02:30] Long chapter"
        result = Transcript.process_timestamps(text)
        assert result == "[ts 3750] 1:02:30 Long chapter"

    def test_bracketed_mixed_with_bare(self):
        text = "[00:00] Intro\n5:30 Middle\n[25:49] Closing"
        result = Transcript.process_timestamps(text)
        lines = result.split("\n")
        assert lines[0] == "[ts 0] 00:00 Intro"
        assert lines[1] == "[ts 330] 5:30 Middle"
        assert lines[2] == "[ts 1549] 25:49 Closing"

    def test_parens_wrapping(self):
        text = "(0:00) Intro\n(12:30) Mid"
        result = Transcript.process_timestamps(text)
        assert result == "[ts 0] 0:00 Intro\n[ts 750] 12:30 Mid"

    def test_mixed_leading_noise(self):
        # Unbalanced wrappers like `[(00:00 -- start` should still parse.
        text = "[(00:00 -- Opening\n[1:30 -- Section"
        result = Transcript.process_timestamps(text)
        lines = result.split("\n")
        assert lines[0] == "[ts 0] 00:00 Opening"
        assert lines[1] == "[ts 90] 1:30 Section"

    def test_bullet_prefix(self):
        # Bullets and other glyphs before the timestamp get stripped.
        text = "* 0:00 Intro\n• 1:30 Next"
        result = Transcript.process_timestamps(text)
        lines = result.split("\n")
        assert lines[0] == "[ts 0] 0:00 Intro"
        assert lines[1] == "[ts 90] 1:30 Next"

    def test_colon_separator(self):
        text = "0:00: Intro\n1:30: Next"
        result = Transcript.process_timestamps(text)
        assert result == "[ts 0] 0:00 Intro\n[ts 90] 1:30 Next"

    def test_non_timestamp_line_starts_unchanged(self):
        # Lines that don't have a timestamp at the start must not be touched.
        text = "URL: https://example.com/watch?t=0:00\nAbout the 12:34 ratio"
        result = Transcript.process_timestamps(text)
        assert result == text
