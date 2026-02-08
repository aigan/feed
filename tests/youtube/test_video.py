import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from conftest import BATCH_TIME

from youtube.video import Video

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_video(duration_data="PT0S", **overrides):
    """Create a minimal Video instance for testing."""
    defaults = dict(
        video_id="test123",
        title="Test",
        channel_id="ch1",
        published_at=datetime(2024, 1, 1),
        first_seen=datetime(2024, 1, 1),
        last_updated=datetime(2024, 1, 1),
        description="",
        thumbnails_data={},
        tags=[],
        category_id=1,
        live_status="none",
        duration_data=duration_data,
        spatial_dimension_type="2d",
        resolution_tier="hd",
        captioned=True,
        licensed_content=False,
        content_rating_data={},
        viewing_projection="rectangular",
        privacy_status="public",
        license="youtube",
        embeddable=True,
        public_stats_viewable=True,
        made_for_kids=False,
        view_count=0,
        like_count=0,
        comment_count=0,
        topic_details={},
        has_paid_product_placement=False,
    )
    defaults.update(overrides)
    return Video(**defaults)


def _sample_video_data(**overrides):
    """Return a dict that looks like what Video.retrieve() returns."""
    base = {
        "video_id": "vid_ABCDEF",
        "title": "Sample Video",
        "channel_id": "UC_xyz",
        "published_at": "2024-06-01T12:00:00+00:00",
        "description": "A description",
        "thumbnails_data": {"default": {"url": "http://img"}},
        "tags": ["tag1", "tag2"],
        "category_id": "22",
        "live_status": "none",
        "live_start": None,
        "live_chat_id": None,
        "recording_date": None,
        "duration_data": "PT10M",
        "spatial_dimension_type": "2d",
        "resolution_tier": "hd",
        "captioned": "true",
        "licensed_content": True,
        "content_rating_data": {},
        "viewing_projection": "rectangular",
        "privacy_status": "public",
        "license": "youtube",
        "embeddable": True,
        "public_stats_viewable": True,
        "made_for_kids": False,
        "view_count": "100",
        "like_count": "10",
        "comment_count": "5",
        "topic_details": None,
        "has_paid_product_placement": False,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Path construction (existing tests, adapted to config.DATA_DIR)
# ---------------------------------------------------------------------------

class TestVideoPathConstruction:
    def test_get_active_dir_shards_by_two_char_prefix(self, ctx):
        result = Video.get_active_dir("abcdef12345")
        assert result == ctx / "youtube/videos/active/ab/abcdef12345"

    def test_get_archive_dir_shards_by_two_char_prefix(self, ctx):
        result = Video.get_archive_dir("XYz123")
        assert result == ctx / "youtube/videos/archive/XY/XYz123"

    def test_get_processed_dir_is_subdir_of_active(self, ctx):
        result = Video.get_processed_dir("abcdef12345")
        assert result == ctx / "youtube/videos/active/ab/abcdef12345/processed"


# ---------------------------------------------------------------------------
# Duration formatting (existing tests, unchanged)
# ---------------------------------------------------------------------------

class TestDurationFormatted:
    def test_minutes_and_seconds(self):
        assert _make_video("PT5M30S").duration_formatted == "5:30"

    def test_hours_minutes_seconds(self):
        assert _make_video("PT1H2M3S").duration_formatted == "1:02:03"

    def test_zero_duration(self):
        assert _make_video("PT0S").duration_formatted == "0:00"

    def test_seconds_only(self):
        assert _make_video("PT45S").duration_formatted == "0:45"

    def test_hours_only(self):
        assert _make_video("PT2H").duration_formatted == "2:00:00"


# ---------------------------------------------------------------------------
# Video.update  — file-DB integration tests
# ---------------------------------------------------------------------------

class TestVideoUpdate:
    def test_first_update_creates_file_with_first_seen(self, ctx, read_json):
        retrieve_data = _sample_video_data()
        with patch.object(Video, "retrieve", return_value=retrieve_data):
            Video.update("vid_ABCDEF")

        data = read_json("youtube/videos/active/vi/vid_ABCDEF/video.json")
        assert data["first_seen"] == BATCH_TIME.isoformat()
        assert data["last_updated"] == BATCH_TIME.isoformat()
        assert data["title"] == "Sample Video"

    def test_update_no_change_does_not_archive(self, ctx, write_json, read_json):
        retrieve_data = _sample_video_data()
        existing = dict(retrieve_data,
                        first_seen=BATCH_TIME.isoformat(),
                        last_updated=BATCH_TIME.isoformat())
        write_json("youtube/videos/active/vi/vid_ABCDEF/video.json", existing)

        with patch.object(Video, "retrieve", return_value=retrieve_data):
            Video.update("vid_ABCDEF")

        archive_dir = ctx / "youtube/videos/archive/vi/vid_ABCDEF"
        assert not archive_dir.exists()

    def test_update_with_change_creates_archive_v1(self, ctx, write_json, read_json):
        retrieve_data = _sample_video_data(title="New Title")
        existing = dict(_sample_video_data(title="Old Title"),
                        first_seen=BATCH_TIME.isoformat(),
                        last_updated=BATCH_TIME.isoformat())
        write_json("youtube/videos/active/vi/vid_ABCDEF/video.json", existing)

        with patch.object(Video, "retrieve", return_value=retrieve_data):
            Video.update("vid_ABCDEF")

        archive = read_json("youtube/videos/archive/vi/vid_ABCDEF/v1.json")
        assert archive["title"] == "Old Title"

        active = read_json("youtube/videos/active/vi/vid_ABCDEF/video.json")
        assert active["title"] == "New Title"

    def test_update_stat_change_only_does_not_archive(self, ctx, write_json):
        retrieve_data = _sample_video_data(view_count="999")
        existing = dict(_sample_video_data(view_count="100"),
                        first_seen=BATCH_TIME.isoformat(),
                        last_updated=BATCH_TIME.isoformat())
        write_json("youtube/videos/active/vi/vid_ABCDEF/video.json", existing)

        with patch.object(Video, "retrieve", return_value=retrieve_data):
            Video.update("vid_ABCDEF")

        archive_dir = ctx / "youtube/videos/archive/vi/vid_ABCDEF"
        assert not archive_dir.exists()

    def test_successive_changes_create_v1_then_v2(self, ctx, write_json, read_json):
        # First archive already exists
        write_json("youtube/videos/archive/vi/vid_ABCDEF/v1.json",
                    _sample_video_data(title="V1 Title"))
        existing = dict(_sample_video_data(title="V2 Title"),
                        first_seen=BATCH_TIME.isoformat(),
                        last_updated=BATCH_TIME.isoformat())
        write_json("youtube/videos/active/vi/vid_ABCDEF/video.json", existing)

        retrieve_data = _sample_video_data(title="V3 Title")
        with patch.object(Video, "retrieve", return_value=retrieve_data):
            Video.update("vid_ABCDEF")

        v2 = read_json("youtube/videos/archive/vi/vid_ABCDEF/v2.json")
        assert v2["title"] == "V2 Title"

        active = read_json("youtube/videos/active/vi/vid_ABCDEF/video.json")
        assert active["title"] == "V3 Title"


# ---------------------------------------------------------------------------
# Video.get  — file-DB integration tests
# ---------------------------------------------------------------------------

class TestVideoGet:
    def test_get_loads_from_existing_file(self, ctx, write_json):
        data = dict(_sample_video_data(),
                     first_seen=BATCH_TIME.isoformat(),
                     last_updated=BATCH_TIME.isoformat())
        write_json("youtube/videos/active/vi/vid_ABCDEF/video.json", data)

        video = Video.get("vid_ABCDEF")
        assert video.title == "Sample Video"
        assert video.video_id == "vid_ABCDEF"

    def test_get_missing_file_calls_update(self, ctx):
        retrieve_data = _sample_video_data()
        with patch.object(Video, "retrieve", return_value=retrieve_data):
            video = Video.get("vid_ABCDEF")

        assert video.title == "Sample Video"


# ---------------------------------------------------------------------------
# Video.retrieve  — API response transformation
# ---------------------------------------------------------------------------

class TestVideoRetrieve:
    def _make_api_response(self, **overrides):
        """Build a fake YouTube API response dict."""
        item = {
            "snippet": {
                "title": "API Title",
                "channelId": "UC_chan",
                "publishedAt": "2024-06-01T00:00:00Z",
                "description": "desc",
                "thumbnails": {"default": {"url": "http://thumb"}},
                "tags": ["t1", "t2"],
                "categoryId": "22",
                "liveBroadcastContent": "none",
            },
            "contentDetails": {
                "duration": "PT5M",
                "dimension": "2d",
                "definition": "hd",
                "caption": "true",
                "licensedContent": True,
                "contentRating": {},
                "projection": "rectangular",
            },
            "liveStreamingDetails": {},
            "recordingDetails": {},
            "statistics": {
                "viewCount": "42",
                "likeCount": "7",
                "commentCount": "3",
            },
            "status": {
                "privacyStatus": "public",
                "license": "youtube",
                "embeddable": True,
                "publicStatsViewable": True,
                "madeForKids": False,
            },
            "topicDetails": {"topicIds": ["/m/02vx4"]},
            "paidProductPlacementDetails": {},
        }
        item.update(overrides)
        return {"items": [item]}

    def _mock_client(self, response):
        mock_client = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = response
        mock_client.videos.return_value.list.return_value = mock_request
        return mock_client

    def test_transforms_full_response_to_flat_dict(self):
        response = self._make_api_response()
        mock_client = self._mock_client(response)

        with patch("youtube.get_youtube_client", return_value=mock_client):
            result = Video.retrieve("vid123")

        assert result["video_id"] == "vid123"
        assert result["title"] == "API Title"
        assert result["channel_id"] == "UC_chan"
        assert result["duration_data"] == "PT5M"
        assert result["view_count"] == "42"

    def test_missing_optional_sections_become_none(self):
        response = self._make_api_response()
        mock_client = self._mock_client(response)

        with patch("youtube.get_youtube_client", return_value=mock_client):
            result = Video.retrieve("vid123")

        assert result["live_start"] is None
        assert result["live_chat_id"] is None
        assert result["recording_date"] is None

    def test_tags_preserved_as_list(self):
        response = self._make_api_response()
        mock_client = self._mock_client(response)

        with patch("youtube.get_youtube_client", return_value=mock_client):
            result = Video.retrieve("vid123")

        assert result["tags"] == ["t1", "t2"]


# ---------------------------------------------------------------------------
# Video.update  — corruption edge cases
# ---------------------------------------------------------------------------

class TestVideoUpdateCorruption:
    def test_update_corrupted_json_raises(self, ctx, write_raw):
        write_raw("youtube/videos/active/vi/vid_ABCDEF/video.json", "NOT JSON{{{")
        with patch.object(Video, "retrieve", return_value=_sample_video_data()):
            with pytest.raises(json.JSONDecodeError):
                Video.update("vid_ABCDEF")

    def test_update_empty_json_object_raises_on_archive(self, ctx, write_json):
        # BUG: {} takes the exists-branch, diff detects changes, but archive() fails
        # because data['video_id'] is missing
        write_json("youtube/videos/active/vi/vid_ABCDEF/video.json", {})
        with patch.object(Video, "retrieve", return_value=_sample_video_data()):
            with pytest.raises(KeyError):
                Video.update("vid_ABCDEF")

    def test_update_empty_json_no_first_seen(self, ctx, write_json, read_json):
        # BUG: {} takes the exists-branch which skips first_seen injection.
        # If the diff is empty (e.g. data matches retrieve), no archive needed and no crash.
        # But with {}, diff is always non-empty → KeyError on archive (see above).
        # This test documents the no-first_seen bug for existing data that *doesn't* diff.
        retrieve_data = _sample_video_data()
        existing = dict(retrieve_data)  # same as retrieve, so no diff
        write_json("youtube/videos/active/vi/vid_ABCDEF/video.json", existing)
        with patch.object(Video, "retrieve", return_value=retrieve_data):
            Video.update("vid_ABCDEF")

        active = read_json("youtube/videos/active/vi/vid_ABCDEF/video.json")
        # No first_seen because file existed → took the exists-branch, no diff → no archive
        assert "first_seen" not in active


# ---------------------------------------------------------------------------
# Video.get  — corruption edge cases
# ---------------------------------------------------------------------------

class TestVideoGetCorruption:
    def test_get_corrupted_json_raises(self, ctx, write_raw):
        write_raw("youtube/videos/active/vi/vid_ABCDEF/video.json", "NOT JSON{{{")
        with pytest.raises(json.JSONDecodeError):
            Video.get("vid_ABCDEF")

    def test_get_missing_required_fields_raises(self, ctx, write_json):
        write_json("youtube/videos/active/vi/vid_ABCDEF/video.json",
                    {"video_id": "x", "title": "y"})
        with pytest.raises(TypeError):
            Video.get("vid_ABCDEF")


# ---------------------------------------------------------------------------
# Video archive  — edge cases
# ---------------------------------------------------------------------------

class TestVideoArchiveEdgeCases:
    def test_latest_version_no_archive_dir(self, ctx):
        assert Video.latest_version("nonexistent") == 0

    def test_latest_version_malformed_filename_raises(self, ctx, write_raw):
        write_raw("youtube/videos/archive/vi/vid_ABCDEF/v1a.json", "{}")
        with pytest.raises(ValueError):
            Video.latest_version("vid_ABCDEF")

    def test_latest_version_gap_returns_max(self, ctx, write_json):
        write_json("youtube/videos/archive/vi/vid_ABCDEF/v1.json", {})
        write_json("youtube/videos/archive/vi/vid_ABCDEF/v3.json", {})
        assert Video.latest_version("vid_ABCDEF") == 3

    def test_archive_after_gap_creates_next(self, ctx, write_json, read_json):
        write_json("youtube/videos/archive/vi/vid_ABCDEF/v1.json", {"title": "v1"})
        write_json("youtube/videos/archive/vi/vid_ABCDEF/v3.json", {"title": "v3"})

        existing = dict(_sample_video_data(title="Old Title"),
                        first_seen=BATCH_TIME.isoformat(),
                        last_updated=BATCH_TIME.isoformat())
        write_json("youtube/videos/active/vi/vid_ABCDEF/video.json", existing)

        with patch.object(Video, "retrieve", return_value=_sample_video_data(title="New Title")):
            Video.update("vid_ABCDEF")

        # v4 created (max was 3, +1)
        v4 = read_json("youtube/videos/archive/vi/vid_ABCDEF/v4.json")
        assert v4["title"] == "Old Title"
        # v2 still missing
        assert not (ctx / "youtube/videos/archive/vi/vid_ABCDEF/v2.json").exists()


# ---------------------------------------------------------------------------
# Video.retrieve  — API error edge cases
# ---------------------------------------------------------------------------

class TestVideoRetrieveErrors:
    def _mock_client(self, response):
        mock_client = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = response
        mock_client.videos.return_value.list.return_value = mock_request
        return mock_client

    def test_retrieve_empty_items_raises(self):
        mock_client = self._mock_client({"items": []})
        with patch("youtube.get_youtube_client", return_value=mock_client):
            with pytest.raises(IndexError):
                Video.retrieve("vid_deleted")

    def test_retrieve_no_items_key_raises(self):
        mock_client = self._mock_client({})
        with patch("youtube.get_youtube_client", return_value=mock_client):
            with pytest.raises(KeyError):
                Video.retrieve("vid_deleted")


# ---------------------------------------------------------------------------
# Video.transcript  — edge cases
# ---------------------------------------------------------------------------

class TestVideoTranscriptEdgeCases:
    def test_transcript_download_none_caches_null(self, ctx):
        video = _make_video("PT5M", video_id="vid_ABCDEF")
        with patch("youtube.transcript.Transcript.download", return_value=None):
            result = video.transcript()

        assert result is None
        data_file = ctx / "youtube/videos/active/vi/vid_ABCDEF/transcript.json"
        assert data_file.exists()
        assert data_file.read_text().strip() == "null"

    def test_transcript_cached_null_returns_none(self, ctx, write_raw):
        write_raw("youtube/videos/active/vi/vid_ABCDEF/transcript.json", "null")
        video = _make_video("PT5M", video_id="vid_ABCDEF")
        result = video.transcript()
        assert result is None

    def test_transcript_corrupted_json_raises(self, ctx, write_raw):
        write_raw("youtube/videos/active/vi/vid_ABCDEF/transcript.json", "NOT JSON{{{")
        video = _make_video("PT5M", video_id="vid_ABCDEF")
        with pytest.raises(json.JSONDecodeError):
            video.transcript()
