import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from youtube.subscription import Subscription
from util import to_obj
from conftest import BATCH_TIME


# ---------------------------------------------------------------------------
# Subscription.update_from_data  — file-DB integration tests
# ---------------------------------------------------------------------------

class TestSubscriptionUpdateFromData:
    def _make_item(self, channel_id="UC_sub1", title="Sub Channel"):
        """Build a SafeNamespace that mimics an API subscription item."""
        return to_obj({
            "id": "sub_id_1",
            "snippet": {
                "title": title,
                "resourceId": {"channelId": channel_id},
            },
            "contentDetails": {
                "activityType": "upload",
                "newItemCount": 3,
                "totalItemCount": 50,
            },
        })

    def test_new_subscription_creates_file_with_first_seen(self, ctx, read_json):
        item = self._make_item()
        Subscription.update_from_data(item)

        data = read_json("youtube/subscriptions/active/UC_sub1.json")
        assert data["first_seen"] == BATCH_TIME.isoformat()
        assert data["channel_id"] == "UC_sub1"
        assert data["title"] == "Sub Channel"

    def test_existing_subscription_preserves_first_seen(self, ctx, write_json, read_json):
        old_time = "2024-01-01T00:00:00+00:00"
        write_json("youtube/subscriptions/active/UC_sub1.json", {
            "channel_id": "UC_sub1",
            "title": "Old Title",
            "subscription_id": "sub_id_1",
            "first_seen": old_time,
            "last_updated": old_time,
            "activity_type": "upload",
            "new_item_count": 0,
            "total_item_count": 40,
        })

        item = self._make_item(title="New Title")
        Subscription.update_from_data(item)

        data = read_json("youtube/subscriptions/active/UC_sub1.json")
        assert data["first_seen"] == old_time  # preserved
        assert data["title"] == "New Title"     # updated
        assert data["total_item_count"] == 50   # updated


# ---------------------------------------------------------------------------
# Subscription.archive_unsubscribed  — file-DB integration tests
# ---------------------------------------------------------------------------

class TestSubscriptionArchive:
    def test_archive_unsubscribed_moves_file_adds_timestamp(self, ctx, write_json, read_json):
        write_json("youtube/subscriptions/active/UC_gone.json", {
            "channel_id": "UC_gone",
            "title": "Gone Channel",
            "first_seen": "2024-01-01T00:00:00+00:00",
        })

        Subscription.archive_unsubscribed("UC_gone")

        # Active file should be deleted
        assert not (ctx / "youtube/subscriptions/active/UC_gone.json").exists()

        # Archive file should exist with unsubscribed_at
        archive = read_json("youtube/subscriptions/archive/2025/UC_gone.json")
        assert archive["unsubscribed_at"] == BATCH_TIME.isoformat()
        assert archive["title"] == "Gone Channel"

    def test_archive_nonexistent_file_is_safe(self, ctx):
        # Should not raise
        Subscription.archive_unsubscribed("UC_nonexistent")


# ---------------------------------------------------------------------------
# Subscription.get_all  — edge cases
# ---------------------------------------------------------------------------

class TestSubscriptionGetAllEdgeCases:
    def test_get_all_empty_dir_yields_nothing(self, ctx):
        # Create the directory but leave it empty
        (ctx / "youtube/subscriptions/active").mkdir(parents=True, exist_ok=True)
        assert list(Subscription.get_all()) == []

    def test_get_all_corrupted_json_raises(self, ctx, write_raw):
        write_raw("youtube/subscriptions/active/UC_bad.json", "NOT JSON{{{")
        with pytest.raises(json.JSONDecodeError):
            list(Subscription.get_all())

    def test_get_all_missing_field_raises(self, ctx, write_json):
        write_json("youtube/subscriptions/active/UC_partial.json", {
            "channel_id": "UC_partial",
            "first_seen": "2024-01-01T00:00:00+00:00",
            "last_updated": "2024-01-01T00:00:00+00:00",
        })
        with pytest.raises(TypeError):
            list(Subscription.get_all())

    def test_get_all_extra_fields_raises(self, ctx, write_json):
        write_json("youtube/subscriptions/active/UC_extra.json", {
            "channel_id": "UC_extra",
            "subscription_id": "sub_1",
            "first_seen": "2024-01-01T00:00:00+00:00",
            "last_updated": "2024-01-01T00:00:00+00:00",
            "activity_type": "upload",
            "new_item_count": 0,
            "total_item_count": 10,
            "title": "Extra Channel",
            "extra": "boom",
        })
        with pytest.raises(TypeError):
            list(Subscription.get_all())


# ---------------------------------------------------------------------------
# Subscription archive  — edge cases
# ---------------------------------------------------------------------------

class TestSubscriptionArchiveEdgeCases:
    def test_archive_destination_exists_overwrites(self, ctx, write_json, read_json):
        write_json("youtube/subscriptions/active/UC_dup.json", {
            "channel_id": "UC_dup",
            "title": "New Data",
            "first_seen": "2024-01-01T00:00:00+00:00",
        })
        write_json("youtube/subscriptions/archive/2025/UC_dup.json", {
            "channel_id": "UC_dup",
            "title": "Old Archive",
        })

        Subscription.archive_unsubscribed("UC_dup")

        archive = read_json("youtube/subscriptions/archive/2025/UC_dup.json")
        assert archive["title"] == "New Data"
        assert archive["unsubscribed_at"] == BATCH_TIME.isoformat()

    def test_update_from_data_corrupted_existing_raises(self, ctx, write_raw):
        write_raw("youtube/subscriptions/active/UC_bad.json", "NOT JSON{{{")

        item = to_obj({
            "id": "sub_id_1",
            "snippet": {
                "title": "Channel",
                "resourceId": {"channelId": "UC_bad"},
            },
            "contentDetails": {
                "activityType": "upload",
                "newItemCount": 0,
                "totalItemCount": 10,
            },
        })
        with pytest.raises(json.JSONDecodeError):
            Subscription.update_from_data(item)
