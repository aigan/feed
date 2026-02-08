# Backlog

Bugs discovered by edge case tests. Each entry references the test that documents the behavior.

## 1. Video.update crashes on existing file missing `video_id`

If `video.json` exists but lacks `video_id` (e.g. `{}` from a partial write), `update()` takes the exists-branch, DeepDiff detects changes, then `archive()` crashes on `data['video_id']`.

- **Location:** `lib/youtube/video.py:176`
- **Test:** `test_video.py::TestVideoUpdateCorruption::test_update_empty_json_object_raises_on_archive`
- **Impact:** Crash on corrupted/partially-written files. No recovery path.

## 2. Video.update skips `first_seen` for pre-existing files

The exists-branch never injects `first_seen` — it only does `data.update(new_data)`. If the existing file lacks `first_seen` for any reason, the updated file will also lack it. The `first_seen` injection only happens in the else-branch (new file).

- **Location:** `lib/youtube/video.py:101-122`
- **Test:** `test_video.py::TestVideoUpdateCorruption::test_update_empty_json_no_first_seen`
- **Impact:** Silent data loss. Videos updated from corrupted files permanently lose their `first_seen` timestamp.

## 3. Channel.update crashes on existing file missing `channel_id`

Same pattern as #1. Empty `{}` triggers `migrate()` → `migrate_v1()` produces `{'schema_version': 2, 'uploads_count': None}` with no `channel_id`. Then `archive()` crashes on `old['channel_id']`.

- **Location:** `lib/youtube/channel.py:339`
- **Test:** `test_channel.py::TestChannelUpdateCorruption::test_update_empty_json_triggers_migration_then_raises`
- **Impact:** Crash on corrupted/partially-written files. No recovery path.

## 4. Channel.migrate calls `None()` on unknown schema version

`MIGRATIONS.get(unknown_version)` returns `None`, then `func(data)` calls `None(data)` → `TypeError: 'NoneType' object is not callable`. No meaningful error message.

- **Location:** `lib/youtube/channel.py:371`
- **Test:** `test_channel.py::TestChannelMigrateEdgeCases::test_migrate_unknown_version_raises`
- **Impact:** Confusing error. Should raise a clear "unsupported schema version" message.

## 5. Channel.get silently accepts future schema versions

The check `data.get('schema_version', 0) >= SCHEMA_VERSION` means any schema_version higher than current (e.g. 99) is silently accepted. If a future version adds required fields, older code will load it without complaint.

- **Location:** `lib/youtube/channel.py:67`
- **Test:** `test_channel.py::TestChannelMigrateEdgeCases::test_get_future_schema_version_accepted`
- **Impact:** Low risk currently but could cause subtle breakage if schema versions are ever used across environments.

## 6. Rating.find_log_tail off-by-one with `lines[-0:]`

When `offset=0` and the match is at `i=0` in the reversed iteration, the code returns `lines[-0:]`. In Python, `lines[-0:]` is `lines[0:]` — the entire list. So when the most recent log line matches the query timestamp, it returns all lines instead of an empty tail.

- **Location:** `lib/youtube/ratings.py:98`
- **Tests:** `test_rating.py::TestFindLogTailEdgeCases::test_offset_zero_match_last_line_returns_all`, `test_rating.py::TestFindLogTailEdgeCases::test_single_line_offset_zero`
- **Impact:** Over-reports unrated videos. The unlike-detection logic receives too many log entries, potentially archiving ratings that shouldn't be archived.

## 7. Channel.archive_uploads crashes on empty `new` list

`archive_uploads()` accesses `new[0][1]` without checking if `new` is empty.

- **Location:** `lib/youtube/channel.py:197`
- **Test:** `test_channel.py::TestChannelUploadsEdgeCases::test_archive_uploads_empty_new_raises`
- **Impact:** `IndexError` with no useful context if called with empty data.

## 8. Channel.update_uploads_from_data crashes on empty buffer

`buffer_data[0][1].year` crashes with `IndexError` when called with `[]`. The caller (`remote_uploads`) could pass an empty buffer if the API returns no items at a year boundary.

- **Location:** `lib/youtube/channel.py:156`
- **Test:** `test_channel.py::TestChannelUploadsEdgeCases::test_update_uploads_empty_buffer_raises`
- **Impact:** `IndexError` crash during upload mirroring if API returns unexpected empty batches.
