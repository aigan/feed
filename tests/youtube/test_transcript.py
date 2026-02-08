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

    def test_timestamp_with_dash_separator(self):
        text = "3:45 - Some topic"
        result = Transcript.process_timestamps(text)
        assert result == "[ts 225] 3:45 - Some topic"
