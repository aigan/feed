import json

import pytest
from conftest import BATCH_TIME

from youtube.ratings import Rating

# ---------------------------------------------------------------------------
# Rating.archive_undone_ratings  — file-DB integration tests
# ---------------------------------------------------------------------------

class TestRatingArchiveUndone:
    def test_archive_moves_file_and_adds_unrated_at(self, ctx, write_json, read_json):
        write_json("youtube/likes/active/vid_abc.json", {
            "first_seen": "2024-06-01T00:00:00+00:00",
            "video": {"id": "vid_abc"},
        })

        rating = Rating("like", BATCH_TIME)
        rating.archive_undone_ratings({"vid_abc"})

        # Active file removed
        assert not (ctx / "youtube/likes/active/vid_abc.json").exists()

        # Archive file exists
        archive = read_json("youtube/likes/archive/2025/vid_abc.json")
        assert archive["unrated_at"] == BATCH_TIME.isoformat()

    def test_archive_nonexistent_file_is_safe(self, ctx):
        rating = Rating("like", BATCH_TIME)
        # Should not raise
        rating.archive_undone_ratings({"vid_nonexistent"})


# ---------------------------------------------------------------------------
# Rating.find_log_tail  — unit tests
# ---------------------------------------------------------------------------

class TestRatingFindLogTail:
    def test_returns_tail_after_oldest_timestamp(self, ctx):
        log_lines = [
            "2024-01-01T00:00:00+00:00 vid_old",
            "2024-06-01T00:00:00+00:00 vid_mid",
            "2024-09-01T00:00:00+00:00 vid_new",
        ]
        log_path = ctx / "youtube/likes/likes.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_lines))

        rating = Rating("like", BATCH_TIME)
        # offset=0, oldest_timestamp="2024-01-01..." matches vid_old at i=2
        # returns lines[-2:] = [vid_mid, vid_new]
        result = rating.find_log_tail("2024-01-01T00:00:00+00:00", 0)
        assert len(result) == 2
        assert "vid_mid" in result[0]
        assert "vid_new" in result[1]

    def test_empty_log_returns_empty_list(self, ctx):
        rating = Rating("like", BATCH_TIME)
        result = rating.find_log_tail("2024-01-01T00:00:00+00:00", 0)
        assert result == []


# ---------------------------------------------------------------------------
# Rating.find_log_tail  — edge cases
# ---------------------------------------------------------------------------

class TestFindLogTailEdgeCases:
    def test_offset_zero_match_last_line_returns_all(self, ctx):
        # BUG: when offset=0 and the match is at i=0, lines[-0:] returns all lines
        log_lines = [
            "2024-01-01T00:00:00+00:00 vid_a",
            "2024-06-01T00:00:00+00:00 vid_b",
            "2024-09-01T00:00:00+00:00 vid_c",
        ]
        log_path = ctx / "youtube/likes/likes.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_lines))

        rating = Rating("like", BATCH_TIME)
        result = rating.find_log_tail("2024-09-01T00:00:00+00:00", 0)
        # BUG: lines[-0:] == all lines, not empty
        assert len(result) == 3

    def test_offset_exceeds_length_returns_all(self, ctx):
        log_lines = [
            "2024-01-01T00:00:00+00:00 vid_a",
            "2024-06-01T00:00:00+00:00 vid_b",
            "2024-09-01T00:00:00+00:00 vid_c",
        ]
        log_path = ctx / "youtube/likes/likes.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_lines))

        rating = Rating("like", BATCH_TIME)
        result = rating.find_log_tail("2024-01-01T00:00:00+00:00", 10)
        assert result == log_lines

    def test_single_line_offset_zero(self, ctx):
        # BUG: single line, offset=0, match at i=0 → lines[-0:] == all
        log_path = ctx / "youtube/likes/likes.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("2024-01-01T00:00:00+00:00 vid_a")

        rating = Rating("like", BATCH_TIME)
        result = rating.find_log_tail("2024-01-01T00:00:00+00:00", 0)
        assert len(result) == 1

    def test_empty_line_in_log_raises(self, ctx):
        log_lines = [
            "2024-01-01T00:00:00+00:00 vid_a",
            "",
            "2024-09-01T00:00:00+00:00 vid_c",
        ]
        log_path = ctx / "youtube/likes/likes.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_lines))

        rating = Rating("like", BATCH_TIME)
        with pytest.raises(IndexError):
            rating.find_log_tail("2024-01-01T00:00:00+00:00", 0)

    def test_no_matching_timestamp_returns_all(self, ctx):
        log_lines = [
            "2025-01-01T00:00:00+00:00 vid_a",
            "2025-06-01T00:00:00+00:00 vid_b",
        ]
        log_path = ctx / "youtube/likes/likes.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_lines))

        rating = Rating("like", BATCH_TIME)
        result = rating.find_log_tail("2024-01-01T00:00:00+00:00", 0)
        assert result == log_lines


# ---------------------------------------------------------------------------
# Rating.archive_undone_ratings  — edge cases
# ---------------------------------------------------------------------------

class TestArchiveUndoneEdgeCases:
    def test_corrupted_source_json_raises(self, ctx, write_raw):
        write_raw("youtube/likes/active/vid_bad.json", "NOT JSON{{{")

        rating = Rating("like", BATCH_TIME)
        with pytest.raises(json.JSONDecodeError):
            rating.archive_undone_ratings({"vid_bad"})

    def test_multiple_videos_one_corrupted_raises(self, ctx, write_json, write_raw):
        write_json("youtube/likes/active/vid_good.json", {
            "first_seen": "2024-06-01T00:00:00+00:00",
            "video": {"id": "vid_good"},
        })
        write_raw("youtube/likes/active/vid_bad.json", "NOT JSON{{{")

        rating = Rating("like", BATCH_TIME)
        with pytest.raises(json.JSONDecodeError):
            rating.archive_undone_ratings({"vid_good", "vid_bad"})

    def test_overwrites_existing_archive(self, ctx, write_json, read_json):
        write_json("youtube/likes/active/vid_dup.json", {
            "first_seen": "2024-06-01T00:00:00+00:00",
            "video": {"id": "vid_dup"},
        })
        write_json("youtube/likes/archive/2025/vid_dup.json", {
            "old": "data",
        })

        rating = Rating("like", BATCH_TIME)
        rating.archive_undone_ratings({"vid_dup"})

        assert not (ctx / "youtube/likes/active/vid_dup.json").exists()
        archive = read_json("youtube/likes/archive/2025/vid_dup.json")
        assert archive["unrated_at"] == BATCH_TIME.isoformat()
        assert archive["video"] == {"id": "vid_dup"}
