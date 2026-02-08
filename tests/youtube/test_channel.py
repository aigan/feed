import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from conftest import BATCH_TIME

from youtube.channel import SCHEMA_VERSION, Channel, PlaylistInaccessibleError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_channel_data(**overrides):
    """Return a dict that looks like what Channel.retrieve() returns."""
    base = {
        "channel_id": "UC_test123",
        "title": "Test Channel",
        "custom_url": "@testchannel",
        "banner_external_url": "http://banner",
        "description": "A test channel",
        "published_at": "2020-01-15T00:00:00+00:00",
        "playlists_data": {"uploads": "UU_test123"},
        "thumbnails": {"default": {"url": "http://thumb"}},
        "view_count": "5000",
        "subscriber_count": "100",
        "uploads_count": "42",
        "status": {"privacyStatus": "public"},
        "topic_details": None,
        "schema_version": SCHEMA_VERSION,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Migration (existing tests, unchanged)
# ---------------------------------------------------------------------------

class TestMigrateV1:
    def test_removes_old_fields_and_renames_video_count(self):
        old = {
            "channel_id": "UC123",
            "title": "Test Channel",
            "schema_version": 1,
            "last_uploads_mirror": "2024-01-01T00:00:00",
            "statistics": {"views": 100},
            "video_count": 42,
        }
        result = Channel.migrate_v1(old)
        assert result["schema_version"] == 2
        assert result["uploads_count"] == 42
        assert "last_uploads_mirror" not in result
        assert "statistics" not in result
        assert "video_count" not in result

    def test_handles_missing_optional_fields(self):
        old = {"channel_id": "UC456", "schema_version": 0}
        result = Channel.migrate_v1(old)
        assert result["schema_version"] == 2
        assert result["uploads_count"] is None

    def test_preserves_other_fields(self):
        old = {
            "channel_id": "UC789",
            "title": "Keep Me",
            "description": "Also keep",
            "schema_version": 1,
            "video_count": 10,
        }
        result = Channel.migrate_v1(old)
        assert result["channel_id"] == "UC789"
        assert result["title"] == "Keep Me"
        assert result["description"] == "Also keep"

    def test_does_not_mutate_input(self):
        old = {
            "channel_id": "UC123",
            "schema_version": 1,
            "last_uploads_mirror": "x",
            "statistics": {},
            "video_count": 5,
        }
        original_keys = set(old.keys())
        Channel.migrate_v1(old)
        assert set(old.keys()) == original_keys


# ---------------------------------------------------------------------------
# Path construction (existing test, adapted to config.DATA_DIR)
# ---------------------------------------------------------------------------

class TestGetActiveDir:
    def test_path_construction(self, ctx):
        result = Channel.get_active_dir("UC_abc123")
        assert result == ctx / "youtube/channels/active/UC_abc123"


# ---------------------------------------------------------------------------
# Channel.update  — file-DB integration tests
# ---------------------------------------------------------------------------

class TestChannelUpdate:
    def test_first_update_creates_file(self, ctx, read_json):
        retrieve_data = _sample_channel_data()
        with patch.object(Channel, "retrieve", return_value=retrieve_data):
            Channel.update("UC_test123")

        data = read_json("youtube/channels/active/UC_test123/channel.json")
        assert data["first_seen"] == BATCH_TIME.isoformat()
        assert data["title"] == "Test Channel"

    def test_update_no_change_no_archive(self, ctx, write_json):
        retrieve_data = _sample_channel_data()
        existing = dict(retrieve_data,
                        first_seen=BATCH_TIME.isoformat(),
                        last_updated=BATCH_TIME.isoformat())
        write_json("youtube/channels/active/UC_test123/channel.json", existing)

        with patch.object(Channel, "retrieve", return_value=retrieve_data):
            Channel.update("UC_test123")

        # BATCH_TIME: 2025-03-15 → week 11
        archive_dir = ctx / "youtube/channels/archive/2025/week-11/UC_test123"
        assert not archive_dir.exists()

    def test_update_with_change_creates_weekly_archive(self, ctx, write_json, read_json):
        retrieve_data = _sample_channel_data(title="New Title")
        existing = dict(_sample_channel_data(title="Old Title"),
                        first_seen=BATCH_TIME.isoformat(),
                        last_updated=BATCH_TIME.isoformat())
        write_json("youtube/channels/active/UC_test123/channel.json", existing)

        with patch.object(Channel, "retrieve", return_value=retrieve_data):
            Channel.update("UC_test123")

        archive = read_json("youtube/channels/archive/2025/week-11/UC_test123/channel.json")
        assert archive["title"] == "Old Title"

        active = read_json("youtube/channels/active/UC_test123/channel.json")
        assert active["title"] == "New Title"

    def test_weekly_archive_is_idempotent(self, ctx, write_json, read_json):
        """If archive already exists for this week, it should not be overwritten."""
        retrieve_data = _sample_channel_data(title="Third Title")

        # Existing active file with second title
        existing = dict(_sample_channel_data(title="Second Title"),
                        first_seen=BATCH_TIME.isoformat(),
                        last_updated=BATCH_TIME.isoformat())
        write_json("youtube/channels/active/UC_test123/channel.json", existing)

        # Pre-existing weekly archive with first title
        write_json("youtube/channels/archive/2025/week-11/UC_test123/channel.json",
                    _sample_channel_data(title="First Title"))

        with patch.object(Channel, "retrieve", return_value=retrieve_data):
            Channel.update("UC_test123")

        # Archive should still be the first title (not overwritten)
        archive = read_json("youtube/channels/archive/2025/week-11/UC_test123/channel.json")
        assert archive["title"] == "First Title"


# ---------------------------------------------------------------------------
# Channel.get  — file-DB integration tests
# ---------------------------------------------------------------------------

class TestChannelGet:
    def test_get_current_schema_loads_from_file(self, ctx, write_json):
        data = dict(_sample_channel_data(),
                     first_seen=BATCH_TIME.isoformat(),
                     last_updated=BATCH_TIME.isoformat())
        write_json("youtube/channels/active/UC_test123/channel.json", data)

        channel = Channel.get("UC_test123")
        assert channel.title == "Test Channel"
        assert channel.channel_id == "UC_test123"

    def test_get_old_schema_triggers_update_with_migration(self, ctx, write_json):
        old_data = dict(_sample_channel_data(schema_version=1),
                        first_seen=BATCH_TIME.isoformat(),
                        last_updated=BATCH_TIME.isoformat(),
                        video_count=42)
        write_json("youtube/channels/active/UC_test123/channel.json", old_data)

        retrieve_data = _sample_channel_data()
        with patch.object(Channel, "retrieve", return_value=retrieve_data):
            channel = Channel.get("UC_test123")

        assert channel.schema_version == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Channel uploads — file-DB integration tests
# ---------------------------------------------------------------------------

class TestChannelUploads:
    def _make_channel(self):
        data = dict(_sample_channel_data(),
                     first_seen=BATCH_TIME.isoformat(),
                     last_updated=BATCH_TIME.isoformat())
        from util import convert_fields
        return Channel(**convert_fields(Channel, data))

    def test_update_uploads_creates_year_file(self, ctx, read_json):
        channel = self._make_channel()
        buffer_data = [
            ("vid1", datetime(2024, 6, 15, tzinfo=timezone.utc)),
            ("vid2", datetime(2024, 6, 10, tzinfo=timezone.utc)),
        ]
        channel.update_uploads_from_data(buffer_data)

        uploads = read_json("youtube/channels/active/UC_test123/uploads/2024.json")
        assert len(uploads) == 2
        assert uploads[0][0] == "vid1"

    def test_update_uploads_merges_with_existing_data(self, ctx, write_json, read_json):
        channel = self._make_channel()

        # Pre-existing uploads
        existing = [
            ["vid_old", "2024-03-01T00:00:00+00:00"],
        ]
        write_json("youtube/channels/active/UC_test123/uploads/2024.json", existing)

        # New uploads (more recent)
        buffer_data = [
            ("vid_new", datetime(2024, 6, 15, tzinfo=timezone.utc)),
        ]
        channel.update_uploads_from_data(buffer_data)

        uploads = read_json("youtube/channels/active/UC_test123/uploads/2024.json")
        ids = [u[0] for u in uploads]
        assert "vid_new" in ids
        assert "vid_old" in ids


# ---------------------------------------------------------------------------
# Channel.retrieve  — API response transformation
# ---------------------------------------------------------------------------

class TestChannelRetrieve:
    def _make_api_response(self):
        item = {
            "id": "UC_chan",
            "snippet": {
                "title": "API Channel",
                "customUrl": "@apichannel",
                "description": "api desc",
                "publishedAt": "2020-01-01T00:00:00Z",
                "thumbnails": {"default": {"url": "http://t"}},
            },
            "brandingSettings": {
                "image": {"bannerExternalUrl": "http://banner"},
            },
            "contentDetails": {
                "relatedPlaylists": {"uploads": "UU_chan"},
            },
            "statistics": {
                "viewCount": "1000",
                "subscriberCount": "50",
                "videoCount": "20",
            },
            "status": {"privacyStatus": "public"},
            "topicDetails": {"topicIds": ["/m/04rlf"]},
        }
        return {"items": [item]}

    def _mock_client(self, response):
        mock_client = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = response
        mock_client.channels.return_value.list.return_value = mock_request
        return mock_client

    def test_transforms_full_response_to_flat_dict(self):
        response = self._make_api_response()
        mock_client = self._mock_client(response)

        with patch("youtube.get_youtube_client", return_value=mock_client):
            result = Channel.retrieve("UC_chan")

        assert result["channel_id"] == "UC_chan"
        assert result["title"] == "API Channel"
        assert result["custom_url"] == "@apichannel"
        assert result["uploads_count"] == "20"
        assert result["schema_version"] == SCHEMA_VERSION

    def test_playlists_data_is_plain_dict(self):
        response = self._make_api_response()
        mock_client = self._mock_client(response)

        with patch("youtube.get_youtube_client", return_value=mock_client):
            result = Channel.retrieve("UC_chan")

        assert isinstance(result["playlists_data"], dict)
        assert result["playlists_data"]["uploads"] == "UU_chan"


# ---------------------------------------------------------------------------
# Channel.update  — corruption edge cases
# ---------------------------------------------------------------------------

class TestChannelUpdateCorruption:
    def test_update_corrupted_json_raises(self, ctx, write_raw):
        write_raw("youtube/channels/active/UC_test123/channel.json", "NOT JSON{{{")
        with patch.object(Channel, "retrieve", return_value=_sample_channel_data()):
            with pytest.raises(json.JSONDecodeError):
                Channel.update("UC_test123")

    def test_update_empty_json_triggers_migration_then_raises(self, ctx):
        # {} has schema_version defaults to 0 via .get('schema_version', 0) → migrate_v1 runs,
        # producing {'schema_version': 2, 'uploads_count': None}, but archive() then raises
        # KeyError because 'channel_id' is missing from the migrated data
        from util import dump_json
        active_dir = ctx / "youtube/channels/active/UC_test123"
        active_dir.mkdir(parents=True, exist_ok=True)
        dump_json(active_dir / "channel.json", {})

        with patch.object(Channel, "retrieve", return_value=_sample_channel_data()):
            with pytest.raises(KeyError):
                Channel.update("UC_test123")


# ---------------------------------------------------------------------------
# Channel.migrate  — edge cases
# ---------------------------------------------------------------------------

class TestChannelMigrateEdgeCases:
    def test_migrate_unknown_version_raises(self):
        with pytest.raises(TypeError):
            Channel.migrate({"schema_version": 5})

    def test_get_future_schema_version_accepted(self, ctx, write_json):
        data = dict(_sample_channel_data(schema_version=99),
                     first_seen=BATCH_TIME.isoformat(),
                     last_updated=BATCH_TIME.isoformat())
        write_json("youtube/channels/active/UC_test123/channel.json", data)

        channel = Channel.get("UC_test123")
        assert channel.schema_version == 99


# ---------------------------------------------------------------------------
# Channel.retrieve  — API error edge cases
# ---------------------------------------------------------------------------

class TestChannelRetrieveErrors:
    def _mock_client(self, response):
        mock_client = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = response
        mock_client.channels.return_value.list.return_value = mock_request
        return mock_client

    def test_retrieve_empty_items_raises(self):
        mock_client = self._mock_client({"items": []})
        with patch("youtube.get_youtube_client", return_value=mock_client):
            with pytest.raises(IndexError):
                Channel.retrieve("UC_deleted")

    def test_retrieve_no_items_key_raises(self):
        mock_client = self._mock_client({})
        with patch("youtube.get_youtube_client", return_value=mock_client):
            with pytest.raises(KeyError):
                Channel.retrieve("UC_deleted")


# ---------------------------------------------------------------------------
# Channel.archive  — edge cases
# ---------------------------------------------------------------------------

class TestChannelArchiveEdgeCases:
    def test_archive_missing_channel_id_raises(self, ctx):
        with pytest.raises(KeyError):
            Channel.archive({}, {"title": "new"})

    def test_archive_stat_change_triggers_archive(self, ctx, read_json):
        old = dict(_sample_channel_data(view_count="100"),
                    first_seen=BATCH_TIME.isoformat(),
                    last_updated=BATCH_TIME.isoformat())
        new = _sample_channel_data(view_count="999")

        Channel.archive(old, new)

        archive = read_json("youtube/channels/archive/2025/week-11/UC_test123/channel.json")
        assert archive["view_count"] == "100"


# ---------------------------------------------------------------------------
# Channel uploads  — edge cases
# ---------------------------------------------------------------------------

class TestChannelUploadsEdgeCases:
    def _make_channel(self):
        data = dict(_sample_channel_data(),
                     first_seen=BATCH_TIME.isoformat(),
                     last_updated=BATCH_TIME.isoformat())
        from util import convert_fields
        return Channel(**convert_fields(Channel, data))

    def test_update_uploads_empty_buffer_raises(self, ctx):
        channel = self._make_channel()
        with pytest.raises(IndexError):
            channel.update_uploads_from_data([])

    def test_update_uploads_corrupted_year_file_raises(self, ctx, write_raw):
        channel = self._make_channel()
        write_raw("youtube/channels/active/UC_test123/uploads/2024.json", "NOT JSON{{{")

        buffer_data = [
            ("vid1", datetime(2024, 6, 15, tzinfo=timezone.utc)),
        ]
        with pytest.raises(json.JSONDecodeError):
            channel.update_uploads_from_data(buffer_data)

    def test_archive_uploads_empty_new_raises(self, ctx):
        channel = self._make_channel()
        old_list = [["vid1", "2024-06-01T00:00:00+00:00"]]
        with pytest.raises(IndexError):
            channel.archive_uploads(old_list, [])

    def test_get_sync_state_corrupted_raises(self, ctx, write_raw):
        channel = self._make_channel()
        write_raw("youtube/channels/active/UC_test123/uploads.json", "NOT JSON{{{")
        with pytest.raises(json.JSONDecodeError):
            channel.get_sync_state()

    def test_get_sync_state_no_file_returns_default(self, ctx):
        channel = self._make_channel()
        state = channel.get_sync_state()
        assert state.first_updated == BATCH_TIME
        assert state.playlist_accessible is True


# ---------------------------------------------------------------------------
# Channel API  — edge cases
# ---------------------------------------------------------------------------

class TestChannelAPIErrors:
    def _make_channel(self, **overrides):
        data = dict(_sample_channel_data(**overrides),
                     first_seen=BATCH_TIME.isoformat(),
                     last_updated=BATCH_TIME.isoformat())
        from util import convert_fields
        return Channel(**convert_fields(Channel, data))

    def test_retrieve_uploads_zero_count_skips_api(self, ctx):
        channel = self._make_channel(uploads_count="0")
        mock_client = MagicMock()
        with patch("youtube.get_youtube_client", return_value=mock_client):
            result = list(channel.retrieve_uploads())
        assert result == []
        mock_client.playlistItems.assert_not_called()

    def test_retrieve_uploads_404_raises_playlist_inaccessible(self, ctx):
        channel = self._make_channel()

        # Mock HttpError for 404
        from googleapiclient.errors import HttpError
        resp = MagicMock()
        resp.status = 404
        http_error = HttpError(resp, b"not found")

        mock_client = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.side_effect = http_error
        mock_client.playlistItems.return_value.list.return_value = mock_request

        # Mock Channel.retrieve succeeding (channel exists, playlist inaccessible)
        with patch("youtube.get_youtube_client", return_value=mock_client), \
             patch.object(Channel, "retrieve", return_value=_sample_channel_data()):
            with pytest.raises(PlaylistInaccessibleError):
                list(channel.retrieve_uploads())
